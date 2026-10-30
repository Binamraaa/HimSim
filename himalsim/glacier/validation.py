"""Comparing the model with reality: observed DEMs and independent field measurements.

Differencing two DEMs gives the *geodetic* thinning rate. ``history.calibrate`` uses
it to tune the climate, and ``band_comparison`` checks *where* the model thins compared
with where the glacier really thinned, elevation band by elevation band. Calibrating on
the glacier-wide average and checking the pattern is a meaningful test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from himalsim.constants import RHO_ICE, RHO_WATER
from himalsim.glacier.model import ICE_THRESHOLD_M
from himalsim.glacier.observations import Measurement
from himalsim.glacier.sites import SiteData
from himalsim.glacier.smb import annual_smb, equilibrium_line_altitude


def geodetic_rate(data: SiteData, year_a: int, year_b: int) -> float:
    """Mean surface-elevation change rate (m/yr) over the initial glacier where both DEMs have data."""
    a, b = data.observed[year_a], data.observed[year_b]
    valid = data.mask & np.isfinite(a) & np.isfinite(b)
    return float(np.mean(b[valid] - a[valid]) / (year_b - year_a))


def band_comparison(data: SiteData, modeled_surface: np.ndarray, year: int, band_m: float = 100.0) -> pd.DataFrame:
    """Observed vs modelled elevation change since ``start_year``, by start-surface elevation band."""
    start_surface = data.observed[data.site.start_year]
    obs = data.observed[year]
    valid = data.mask & np.isfinite(obs) & np.isfinite(start_surface)
    z = start_surface[valid]
    edges = np.arange(np.floor(z.min() / band_m) * band_m, z.max() + band_m, band_m)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = valid & (start_surface >= lo) & (start_surface < hi)
        if sel.sum() < 3:
            continue
        rows.append({
            "band": f"{lo:.0f}-{hi:.0f}",
            "z_mid": 0.5 * (lo + hi),
            "cells": int(sel.sum()),
            "observed_dh": float(np.mean(obs[sel] - start_surface[sel])),
            "modeled_dh": float(np.mean(modeled_surface[sel] - start_surface[sel])),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- independent field measurements

def _by_year(hist) -> dict[int, np.ndarray]:
    start = hist.result.scenario.start_year
    return {int(round(y)) + start: s for y, s in zip(hist.result.snapshot_years, hist.result.snapshots)}


def _year_rows(hist, first: int, last: int) -> np.ndarray:
    """Indices of the yearly diagnostics for calendar years ``first``..``last``."""
    cal = np.round(hist.result.years).astype(int) + hist.result.scenario.start_year
    return np.nonzero((cal >= first) & (cal <= last))[0]


def _centre_thickness(data, hist, year, z_low, z_high):
    """Thickness along the glacier's centre line in an elevation band (by start-year surface).

    Radar profiles follow the centre line, where the ice is thickest, so the model
    equivalent is the thickest quarter of its ice cells in that band (75th percentile).
    """
    h = _by_year(hist)[year]
    z0 = data.observed[data.site.start_year]
    sel = data.mask & (z0 >= z_low) & (z0 <= z_high) & (h > ICE_THRESHOLD_M)
    return float(np.percentile(h[sel], 75)) if sel.any() else 0.0


def _smb_gradient(data, hist, first, last):
    """Mean d(SMB)/dz at the ELA over the years, in m w.e. per 100 m."""
    res, start = hist.result, hist.result.scenario.start_year
    out = []
    for year in range(first, last + 1):
        td, pf = res.scenario.temp_delta(year - start), res.scenario.precip_factor(year - start)
        ela = equilibrium_line_altitude(res.climate, td, pf)
        b = annual_smb(np.array([ela - 50.0, ela + 50.0]), res.climate, td, pf)
        out.append((b[1] - b[0]) * RHO_ICE / RHO_WATER)
    return float(np.mean(out))


MODEL_VALUES = {
    "volume": lambda d, h, year: float(_by_year(h)[year].sum() * d.grid.cell_area / 1e9),
    "area": lambda d, h, year: float((_by_year(h)[year] > ICE_THRESHOLD_M).sum() * d.grid.cell_area / 1e6),
    "centre_thickness": _centre_thickness,
    "mass_balance": lambda d, h, first, last: float(
        h.result.smb_glacier[_year_rows(h, first, last)].mean() * RHO_ICE / RHO_WATER),
    "ela": lambda d, h, first, last: float(np.mean(h.result.ela[_year_rows(h, first, last)])),
    "smb_gradient": _smb_gradient,
}


def _fmt(v: float) -> str:
    """Readable number: no scientific notation, sensible decimals for the magnitude."""
    a = abs(v)
    return f"{v:,.0f}" if a >= 100 else f"{v:.1f}" if a >= 10 else f"{v:.2f}" if a >= 0.1 else f"{v:.3f}"


def reality_check(data: SiteData, hist) -> pd.DataFrame:
    """The model against every measurement: DEM thinning rates plus the site's field data.

    The thinning rate over the calibration period is excluded (it was used to tune the model).
    """
    rows = []
    cal = f"{hist.calibration_period[0]}-{hist.calibration_period[1]}"
    for r in hist.rates.itertuples():
        if r.period == cal:
            continue
        m = Measurement(f"How fast did the surface drop, {r.period.replace('-', '–')}?", "geodetic",
                        round(r.observed_m_per_yr, 2), "m/yr", "Yala survey DEMs (this project)")
        rows.append((m, r.modeled_m_per_yr))
    for m in data.site.measurements:
        rows.append((m, MODEL_VALUES[m.kind](data, hist, **dict(m.params))))
    return pd.DataFrame([{
        "question": m.what,
        "measured": m.shown_as or f"{_fmt(m.value)}{'' if m.uncertainty is None else f' ± {m.uncertainty:.2g}'} {m.unit}",
        "model": f"{_fmt(model)} {m.unit}",
        "grade": m.grade(model),
        "why_off": m.why_off,
        "source": m.source,
        "measured_value": m.value,
        "model_value": model,
    } for m, model in rows])


def yearly_mass_balance(hist, observed: dict[int, tuple[float, float]]) -> pd.DataFrame:
    """Model vs measured glacier-wide mass balance (m w.e.) for each measured year."""
    rows = []
    for year, (value, err) in observed.items():
        i = _year_rows(hist, year, year)
        if i.size:
            rows.append({"year": year, "measured": value, "uncertainty": err,
                         "model": float(hist.result.smb_glacier[i[0]] * RHO_ICE / RHO_WATER)})
    return pd.DataFrame(rows)
