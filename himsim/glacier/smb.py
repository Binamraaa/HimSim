"""Surface mass balance (SMB): how much ice a point gains or loses per year.

Month by month through a balance year that starts on 1 October (after the monsoon melt season),
with a simple snowpack:

    snowfall = P_month x (fraction of P_month that falls as snow), added to the snowpack
    melt     = the snowpack melts first, at the snow rate; once it is gone the rest of the month
               melts ice at the ice rate (bare ice is darker than snow, so it melts faster)
    SMB      = (snowfall - melt), converted from water equivalent to ice

Melt rate per day, two rules (``ClimateParams.melt_model``):

    "ti"  (degree days)            DDF x max(T_month - T_melt, 0), with DDF_snow or DDF_ice
    "eti" (enhanced temp. index)   TF x E[max(T_day - T_melt, 0)] + SRF x SW_in x (1 - albedo) x P(T_day > T_melt)

For "eti" the daily temperatures of a month are taken as normally distributed around the
monthly mean with the measured day-to-day spread, so the sunshine term switches on gradually
as more days of the month rise above freezing, instead of jumping when the monthly mean does.

Snow left at the end of the year is the year's accumulation; older firn is treated like ice.

Positive SMB (high, cold) is the accumulation zone; negative SMB (low, warm) is
the ablation zone. The equilibrium-line altitude (ELA) is where SMB = 0.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr

from himsim.constants import WE_TO_ICE
from himsim.glacier.climate import DAYS_IN_MONTH, ClimateParams


BALANCE_YEAR_START = 10  # October: the snowpack is empty at the start of each balance year


def annual_smb(z: np.ndarray, climate: ClimateParams, temp_delta: float = 0.0, precip_factor: float = 1.0) -> np.ndarray:
    """Annual SMB in metres of ice per year at surface elevations ``z``."""
    z = np.asarray(z, dtype=np.float64)
    temp = climate.monthly_temperature(z, temp_delta)
    precip = climate.monthly_precipitation(z, precip_factor)
    days = DAYS_IN_MONTH.reshape((12,) + (1,) * z.ndim)

    snow_fraction = np.clip((climate.t_rain - temp) / (climate.t_rain - climate.t_snow), 0.0, 1.0)
    snowfall = precip * snow_fraction
    rate_snow, rate_ice = melt_rates(temp, climate)  # m w.e. per day, shape (12, *z.shape)

    snowpack = np.zeros(z.shape)
    melt = np.zeros(z.shape)
    for m in [(BALANCE_YEAR_START - 1 + k) % 12 for k in range(12)]:
        snowpack = snowpack + snowfall[m]
        can_melt = rate_snow[m] * days[m]
        snow_melt = np.minimum(snowpack, can_melt)
        snowpack = snowpack - snow_melt
        snow_covered = np.divide(snow_melt, can_melt, out=np.ones(z.shape), where=can_melt > 0)  # share of the month
        melt = melt + snow_melt + rate_ice[m] * days[m] * (1.0 - snow_covered)

    return (snowfall.sum(axis=0) - melt) * WE_TO_ICE


def melt_rates(temp: np.ndarray, climate: ClimateParams) -> tuple[np.ndarray, np.ndarray]:
    """Melt per day (m w.e.) on snow and on bare ice for monthly mean temperatures ``temp`` (12, ...)."""
    excess = temp - climate.t_melt
    if climate.melt_model == "ti":
        warm = np.maximum(excess, 0.0)
        return climate.ddf_snow * warm, climate.ddf * warm
    if climate.melt_model != "eti":
        raise ValueError(f"unknown melt model {climate.melt_model!r}")
    sd = np.asarray(climate.daily_t_sd, dtype=np.float64).reshape((12,) + (1,) * (temp.ndim - 1))
    sw = np.asarray(climate.sw_in, dtype=np.float64).reshape(sd.shape)
    x = excess / sd
    warm_days = ndtr(x)  # share of days above the melt threshold
    warm = sd * np.exp(-0.5 * x * x) / np.sqrt(2.0 * np.pi) + excess * warm_days  # mean of max(T_day - T_melt, 0)
    sun = climate.srf * sw * warm_days
    return (climate.tf_eti * warm + sun * (1.0 - climate.albedo_snow),
            climate.tf_eti * warm + sun * (1.0 - climate.albedo_ice))


class SmbTable:
    """Annual SMB tabulated against elevation, for fast lookups on a whole grid.

    For a given year SMB depends only on elevation, so computing it on a fine elevation
    axis and interpolating gives the same answer as evaluating every cell, ~50× faster.
    Elevations outside the axis take the end values.
    """

    def __init__(self, z_min: float, z_max: float, step: float = 2.0):
        self.z = np.arange(z_min, z_max + step, step)

    def __call__(self, surface: np.ndarray, climate: ClimateParams, temp_delta: float = 0.0,
                 precip_factor: float = 1.0) -> np.ndarray:
        return np.interp(surface, self.z, annual_smb(self.z, climate, temp_delta, precip_factor))


def equilibrium_line_altitude(climate: ClimateParams, temp_delta: float = 0.0, precip_factor: float = 1.0,
                              z_range: tuple[float, float] = (2000.0, 9000.0)) -> float:
    """Elevation where SMB = 0. Returns NaN if there is no crossing in ``z_range``."""

    def f(z):
        return float(annual_smb(np.array(z), climate, temp_delta, precip_factor))

    lo, hi = z_range
    if np.sign(f(lo)) == np.sign(f(hi)):
        return float("nan")
    return brentq(f, lo, hi, xtol=0.5)


def glacier_wide_smb(surface: np.ndarray, mask: np.ndarray, climate: ClimateParams,
                     temp_delta: float = 0.0, precip_factor: float = 1.0) -> float:
    """Area-averaged SMB (m ice / yr) over the cells in ``mask``."""
    if not mask.any():
        return float("nan")
    return float(annual_smb(surface[mask], climate, temp_delta, precip_factor).mean())


def calibrate_temperature(surface: np.ndarray, mask: np.ndarray, climate: ClimateParams,
                          target_smb: float, search: tuple[float, float] = (-15.0, 15.0),
                          yearly_forcing: list[tuple[float, float]] | None = None) -> ClimateParams:
    """Shift ``t_annual_ref`` so the glacier-wide SMB equals ``target_smb`` (m ice / yr).

    This is the simplest form of model calibration. The real temperature at
    the glacier is uncertain (few stations, lapse rate varies), so a single
    temperature bias absorbs those errors and makes the model reproduce an
    observed quantity: here, the geodetic mass balance from DEM differencing.

    ``yearly_forcing`` is an optional list of ``(temp_delta, precip_factor)``, one per
    observed year. The target is then matched by the *average over those years*, which
    is not the same as the SMB of the average year, because melt only starts above 0 °C.
    """
    forcing = yearly_forcing or [(0.0, 1.0)]

    def misfit(dt):
        shifted = climate.with_changes(t_annual_ref=climate.t_annual_ref + dt)
        return np.mean([glacier_wide_smb(surface, mask, shifted, td, pf) for td, pf in forcing]) - target_smb

    dt = brentq(misfit, *search, xtol=1e-3)
    return climate.with_changes(t_annual_ref=climate.t_annual_ref + dt)
