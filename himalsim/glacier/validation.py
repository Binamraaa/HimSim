"""Validation against observed DEMs ("does the model reproduce reality?").

Differencing two DEMs gives the *geodetic* thinning rate. We use it twice:
  1. Calibration: tune the climate so the glacier-wide SMB matches the observed rate.
  2. Validation: run 1981 -> 2015 (a "hindcast") and compare *where* the model thins
     with where the glacier really thinned, elevation band by elevation band.
Calibrating on (1) and checking (2) is a meaningful test. The calibration only
fixes the glacier-wide average, not the spatial pattern.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from himalsim.glacier.climate import ClimateParams, Scenario
from himalsim.glacier.flow import FlowParams
from himalsim.glacier.model import RunResult, simulate
from himalsim.glacier.sites import SiteData
from himalsim.glacier.smb import calibrate_temperature


def geodetic_rate(data: SiteData, year_a: int, year_b: int) -> float:
    """Mean surface-elevation change rate (m/yr) over the initial glacier where both DEMs have data."""
    a, b = data.observed[year_a], data.observed[year_b]
    valid = data.mask & np.isfinite(a) & np.isfinite(b)
    return float(np.mean(b[valid] - a[valid]) / (year_b - year_a))


def calibrated_climate(data: SiteData, base: ClimateParams = ClimateParams(),
                       period: tuple[int, int] | None = None) -> tuple[ClimateParams, float]:
    """Climate whose glacier-wide SMB on the start surface matches the observed geodetic rate."""
    start = data.site.start_year
    end = period[1] if period else max(data.observed)
    target = geodetic_rate(data, start, end)
    return calibrate_temperature(data.surface, data.mask, base, target), target


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


def hindcast(data: SiteData, climate: ClimateParams, flow: FlowParams = FlowParams(),
             end_year: int | None = None, progress=None) -> tuple[RunResult, dict[int, pd.DataFrame]]:
    """Run from ``start_year`` to ``end_year`` under constant climate; compare with every later DEM."""
    start = data.site.start_year
    end = end_year or max(data.observed)
    scenario = Scenario(name=f"Hindcast {start}-{end}", years=end - start)
    result = simulate(data.bed, data.thickness, data.grid.dx, climate, scenario, flow,
                      accumulation_mask=data.mask, snapshot_every=1, progress=progress)
    comparisons = {}
    for year in sorted(data.observed):
        if start < year <= end:
            idx = int(np.argmin(np.abs(np.array(result.snapshot_years) - (year - start))))
            comparisons[year] = band_comparison(data, data.bed + result.snapshots[idx], year)
    return result, comparisons
