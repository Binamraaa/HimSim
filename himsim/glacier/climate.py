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
    """Baseline climate at a reference elevation and how it changes with height.

    The seasonal cycle is either *measured* (``seasonal_t`` and ``precip_share``, 12 values
    each, usually from ``from_record``) or *idealised* (a cosine with ``t_seasonal_amp`` and
    a monsoon block with ``monsoon_fraction``) when those are left empty.
    """

    ref_elevation: float = 3862.0  # m a.s.l. (Kyanjin Gompa station)
    t_annual_ref: float = 2.5  # °C, annual mean air temperature at ref_elevation (ERA5-Land 1981-2010)
    t_seasonal_amp: float = 7.6  # °C, half the July-January difference (idealised cycle only)
    lapse_rate: float = 0.0060  # °C per metre; temperature drops this much per metre of climb
    p_annual_ref: float = 0.867  # m w.e. per year at ref_elevation (Kyanjin gauge, Immerzeel et al. 2014)
    p_gradient: float = 0.05  # fractional precipitation increase per 100 m of climb
    monsoon_fraction: float = 0.75  # share of annual precipitation falling Jun-Sep (idealised cycle only)
    t_snow: float = 0.0  # °C, at or below this all precipitation is snow
    t_rain: float = 2.0  # °C, at or above this all precipitation is rain
    t_melt: float = 0.0  # °C, melt happens when monthly mean temperature exceeds this
    ddf: float = 0.008  # degree-day factor, m water equivalent per °C per day
    seasonal_t: tuple[float, ...] = ()  # 12 monthly deviations from the annual mean (°C)
    precip_share: tuple[float, ...] = ()  # 12 monthly shares of annual precipitation (sum to 1)
    source: str = "Idealised Langtang climate"

    @classmethod
    def from_record(cls, record, start: int, end: int, **overrides) -> ClimateParams:
        """Climate whose annual means and seasonal cycle are the ``start``-``end`` average of a ClimateRecord."""
        clim = record.climatology(start, end)
        t, p = clim["t_c"].to_numpy(), clim["p_mm"].to_numpy()
        params = dict(
            ref_elevation=record.elevation,
            t_annual_ref=float(t.mean()),
            seasonal_t=tuple(float(v) for v in t - t.mean()),
            p_annual_ref=float(p.sum()) / 1000.0,
            precip_share=tuple(float(v) for v in p / p.sum()),
            source=f"{record.name}, {start}-{end} average",
        )
        params.update(overrides)
        return cls(**params)

    def with_changes(self, **kwargs) -> ClimateParams:
        return replace(self, **kwargs)

    def monthly_precip_share(self) -> np.ndarray:
        """Fraction of annual precipitation falling in each month (sums to 1)."""
        if self.precip_share:
            return np.asarray(self.precip_share, dtype=np.float64)
        share = np.full(12, (1.0 - self.monsoon_fraction) / 8.0)
        share[list(MONSOON_MONTHS)] = self.monsoon_fraction / 4.0
        return share

    def monthly_temperature(self, z: np.ndarray, temp_delta: float = 0.0) -> np.ndarray:
        """Monthly mean temperature (°C), shape ``(12, *z.shape)``."""
        z = np.asarray(z, dtype=np.float64)
        shape = (12,) + (1,) * z.ndim
        if self.seasonal_t:
            seasonal = np.asarray(self.seasonal_t, dtype=np.float64).reshape(shape)
        else:
            months = np.arange(12).reshape(shape)
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

    ``t_anomalies`` / ``p_ratios`` replay *observed* year-to-year weather (one value
    per model year, e.g. from a ClimateRecord); they add to the step change and trend.
    ``trend_years`` stops the trends after that many years (the climate then holds steady).
    ``start_year`` only labels the calendar.
    """

    name: str = "Baseline"
    years: int = 75
    temp_offset: float = 0.0  # °C, step change
    temp_trend: float = 0.0  # °C per decade
    precip_change: float = 0.0  # fraction, e.g. 0.1 = +10 %
    precip_trend: float = 0.0  # fraction per decade
    notes: str = ""
    start_year: int | None = None
    t_anomalies: tuple[float, ...] = ()
    p_ratios: tuple[float, ...] = ()
    trend_years: float | None = None

    def _trend_time(self, t: float) -> float:
        return t if self.trend_years is None else min(t, self.trend_years)

    def _year_index(self, t: float, n: int) -> int:
        return min(int(t), n - 1)

    def temp_delta(self, t: float) -> float:
        observed = self.t_anomalies[self._year_index(t, len(self.t_anomalies))] if self.t_anomalies else 0.0
        return self.temp_offset + self.temp_trend * self._trend_time(t) / 10.0 + observed

    def precip_factor(self, t: float) -> float:
        observed = self.p_ratios[self._year_index(t, len(self.p_ratios))] if self.p_ratios else 1.0
        return max(0.0, (1.0 + self.precip_change) * (1.0 + self.precip_trend * self._trend_time(t) / 10.0) * observed)


@dataclass(frozen=True)
class ClimateChange:
    """The two things a student sets: how much warmer, and how much more (or less) rain and snow.

    Changes are relative to *today's* climate. ``gradual`` changes grow steadily until
    ``target_year`` and then hold; otherwise the full change applies from the start.
    """

    warming: float = 0.0  # °C
    precip: float = 0.0  # fraction, e.g. -0.2 = 20 % less
    gradual: bool = True
    target_year: int = 2100
    notes: str = ""

    def label(self) -> str:
        parts = [f"{self.warming:+.1f} °C"] if self.warming else []
        if self.precip:
            parts.append(f"{100 * self.precip:+.0f} % rain & snow")
        if not parts:
            return "Today's climate continues"
        return ", ".join(parts) + (f" by {self.target_year}" if self.gradual else " from today")

    def scenario(self, start_year: int, end_year: int, name: str | None = None) -> Scenario:
        years = end_year - start_year
        name = name or self.label()
        if self.gradual:
            ramp = max(self.target_year - start_year, 1)
            return Scenario(name, years, temp_trend=10.0 * self.warming / ramp, precip_trend=10.0 * self.precip / ramp,
                            trend_years=ramp, start_year=start_year, notes=self.notes)
        return Scenario(name, years, temp_offset=self.warming, precip_change=self.precip,
                        start_year=start_year, notes=self.notes)


PRESETS: dict[str, ClimateChange] = {
    "Today's climate continues": ClimateChange(notes="The 2016-2025 average climate stays the same."),
    "+1.5 °C by 2100": ClimateChange(1.5, notes="Local temperature rises steadily to 1.5 °C warmer than today in 2100."),
    "+2 °C by 2100": ClimateChange(2.0, notes="Local temperature rises steadily to 2 °C warmer than today in 2100."),
    "+4 °C by 2100": ClimateChange(4.0, notes="Local temperature rises steadily to 4 °C warmer than today in 2100."),
    "Wetter monsoon": ClimateChange(0.0, 0.2, gradual=False, notes="20 % more rain and snow from now on, same temperature."),
    "Warm & dry": ClimateChange(1.0, -0.2, gradual=False, notes="1 °C warmer and 20 % less rain and snow from now on."),
    "Cooler": ClimateChange(-1.0, gradual=False, notes="1 °C colder from now on. Does the glacier grow back?"),
}
