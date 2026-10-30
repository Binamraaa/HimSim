"""Surface mass balance (SMB): how much ice a point gains or loses per year.

Degree-day model, applied month by month:

    melt         = DDF x max(T_month - T_melt, 0) x days_in_month
    accumulation = P_month x (fraction of P_month that falls as snow)
    SMB          = (accumulation - melt), converted from water equivalent to ice

Positive SMB (high, cold) is the accumulation zone; negative SMB (low, warm) is
the ablation zone. The equilibrium-line altitude (ELA) is where SMB = 0.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from himsim.constants import WE_TO_ICE
from himsim.glacier.climate import DAYS_IN_MONTH, ClimateParams


def annual_smb(z: np.ndarray, climate: ClimateParams, temp_delta: float = 0.0, precip_factor: float = 1.0) -> np.ndarray:
    """Annual SMB in metres of ice per year at surface elevations ``z``."""
    z = np.asarray(z, dtype=np.float64)
    temp = climate.monthly_temperature(z, temp_delta)
    precip = climate.monthly_precipitation(z, precip_factor)
    days = DAYS_IN_MONTH.reshape((12,) + (1,) * z.ndim)

    melt = climate.ddf * np.maximum(temp - climate.t_melt, 0.0) * days
    snow_fraction = np.clip((climate.t_rain - temp) / (climate.t_rain - climate.t_snow), 0.0, 1.0)
    accumulation = precip * snow_fraction

    return (accumulation - melt).sum(axis=0) * WE_TO_ICE


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
