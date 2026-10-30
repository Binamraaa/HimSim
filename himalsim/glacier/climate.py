"""Climate forcing: a reference climatology plus human-editable scenarios.

The climate is described at one reference elevation (by default Kyanjin Gompa
station, 3862 m, in the Langtang valley) and extrapolated to the glacier with a
temperature lapse rate and a precipitation gradient. Every month has its own
temperature (seasonal cosine cycle peaking in July) and its own precipitation
(monsoon-dominated, June-September).

The default numbers are approximate Langtang values for teaching. Replace them
with station or reanalysis data (e.g. ERA5) when you have them. ``smb.calibrate``
adjusts the temperature so that the modelled mass balance matches the measured
1981-2015 thinning.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

DAYS_IN_MONTH = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], dtype=np.float64)
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONSOON_MONTHS = (5, 6, 7, 8)  # Jun-Sep, zero-based


@dataclass(frozen=True)
class ClimateParams:
    """Baseline climate at a reference elevation and how it changes with height."""

    ref_elevation: float = 3862.0  # m a.s.l. (Kyanjin Gompa station)
    t_annual_ref: float = 3.5  # °C, annual mean air temperature at ref_elevation
    t_seasonal_amp: float = 7.5  # °C, half the difference between July and January
    lapse_rate: float = 0.0060  # °C per metre; temperature drops this much per metre of climb
    p_annual_ref: float = 0.65  # m water equivalent per year at ref_elevation
    p_gradient: float = 0.05  # fractional precipitation increase per 100 m of climb
    monsoon_fraction: float = 0.75  # share of the annual precipitation falling Jun-Sep
    t_snow: float = 0.0  # °C, at or below this all precipitation is snow
    t_rain: float = 2.0  # °C, at or above this all precipitation is rain
    t_melt: float = 0.0  # °C, melt happens when monthly mean temperature exceeds this
    ddf: float = 0.008  # degree-day factor, m water equivalent per °C per day

    def with_changes(self, **kwargs) -> ClimateParams:
        return replace(self, **kwargs)

    def monthly_precip_share(self) -> np.ndarray:
        """Fraction of annual precipitation falling in each month (sums to 1)."""
        share = np.full(12, (1.0 - self.monsoon_fraction) / 8.0)
        share[list(MONSOON_MONTHS)] = self.monsoon_fraction / 4.0
        return share

    def monthly_temperature(self, z: np.ndarray, temp_delta: float = 0.0) -> np.ndarray:
        """Monthly mean temperature (°C), shape ``(12, *z.shape)``."""
        z = np.asarray(z, dtype=np.float64)
        months = np.arange(12).reshape((12,) + (1,) * z.ndim)
        seasonal = self.t_seasonal_amp * np.cos(2.0 * np.pi * (months - 6) / 12.0)  # peak in July
        annual = self.t_annual_ref + temp_delta - self.lapse_rate * (z - self.ref_elevation)
        return annual[np.newaxis] + seasonal

    def monthly_precipitation(self, z: np.ndarray, precip_factor: float = 1.0) -> np.ndarray:
        """Monthly precipitation (m w.e.), shape ``(12, *z.shape)``."""
        z = np.asarray(z, dtype=np.float64)
        height_factor = np.maximum(0.0, 1.0 + self.p_gradient * (z - self.ref_elevation) / 100.0)
        annual = self.p_annual_ref * precip_factor * height_factor
        share = self.monthly_precip_share().reshape((12,) + (1,) * z.ndim)
        return annual[np.newaxis] * share


@dataclass(frozen=True)
class Scenario:
    """A human-defined "what if": changes applied on top of the baseline climate.

    Changes are relative to the baseline. A step change applies from year 0; a
    trend ramps up linearly. For example ``temp_offset=1, temp_trend=0.3`` means
    +1 °C immediately, then a further +0.3 °C every decade.
    """

    name: str = "Baseline"
    years: int = 100
    temp_offset: float = 0.0  # °C, step change
    temp_trend: float = 0.0  # °C per decade
    precip_change: float = 0.0  # fraction, e.g. 0.1 = +10 %
    precip_trend: float = 0.0  # fraction per decade
    notes: str = ""

    def temp_delta(self, t: float) -> float:
        return self.temp_offset + self.temp_trend * t / 10.0

    def precip_factor(self, t: float) -> float:
        return max(0.0, (1.0 + self.precip_change) * (1.0 + self.precip_trend * t / 10.0))


PRESET_SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in (
        Scenario("Baseline", notes="Calibrated present-day climate held constant."),
        Scenario("Paris +1.5 °C", temp_trend=0.15, notes="Warming ramps to about +1.5 °C after 100 years."),
        Scenario("+2 °C by 2100", temp_trend=0.27, years=75, notes="Mid-range warming over 75 years."),
        Scenario("High emissions +4 °C", temp_trend=0.4, notes="Strong warming; Himalayan high elevations warm faster than the global mean."),
        Scenario("Wetter monsoon +20 %", precip_change=0.2, notes="More precipitation, same temperature."),
        Scenario("Warm & dry", temp_offset=1.0, precip_change=-0.2, notes="+1 °C and 20 % less precipitation."),
        Scenario("Cooling −1 °C", temp_offset=-1.0, notes="Little-Ice-Age-like cooling; the glacier should advance."),
    )
}
