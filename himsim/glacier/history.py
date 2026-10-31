"""Replaying observed climate: calibration, the history run, and "today" as a starting point.

1. Calibrate: find the temperature offset for which the glacier, fed the *actual* 1981-2015
   weather year by year, loses as much ice as the DEMs show.
2. History run: start from the 1981 DEM and replay the observed weather up to the last
   complete year of the climate record. Along the way, compare with the 2007 and 2015 DEMs.
3. Today: the glacier at the end of the history run is the starting point for future
   scenarios, whose baseline is the average temperature of the last decade.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from himsim.climate.record import ClimateRecord
from himsim.glacier.climate import ClimateParams, Scenario
from himsim.glacier.flow import FlowParams
from himsim.glacier.model import RunResult, simulate
from himsim.glacier.sites import SiteData
from himsim.glacier.smb import calibrate_temperature
from himsim.glacier.validation import band_comparison, geodetic_rate
from himsim.store import cached

RECENT_YEARS = 10  # "today's climate" = average of the last decade of the record


@dataclass
class HistoryRun:
    climate: ClimateParams  # calibrated climate of the calibration period
    calibration_period: tuple[int, int]
    target_rate: float  # observed thinning used for calibration (m/yr)
    result: RunResult  # start DEM year -> present, observed weather
    comparisons: dict[int, pd.DataFrame]  # elevation-band comparison at each later DEM year
    rates: pd.DataFrame  # observed vs modelled thinning rate per DEM period
    present_year: int  # the glacier state is for the end of this year
    present_thickness: np.ndarray
    present_climate: ClimateParams  # baseline for future scenarios
    recent_warming: float  # °C, last decade relative to the calibration period


def historical_scenario(record: ClimateRecord, start: int, end: int, base: tuple[int, int]) -> Scenario:
    """Scenario that replays observed years ``start`` .. ``end - 1`` as anomalies relative to ``base``."""
    anom = record.annual_anomalies(*base).loc[start:end - 1]
    if len(anom) != end - start:
        raise ValueError(f"climate record lacks complete years in {start}-{end - 1}")
    return Scenario(name=f"Observed weather {start}-{end}", years=end - start, start_year=start,
                    t_anomalies=tuple(anom["dt_c"]), p_ratios=tuple(anom["p_ratio"]),
                    notes=record.name)


def calibrate(data: SiteData, record: ClimateRecord, base: ClimateParams | None = None,
              period: tuple[int, int] | None = None) -> tuple[ClimateParams, float, tuple[int, int]]:
    """Calibrated climate, the observed target rate, and the calibration period."""
    start = data.site.start_year
    period = period or (start, max(data.observed))
    climate = ClimateParams.from_record(record, *period) if base is None else base
    target = geodetic_rate(data, *period)
    anom = record.annual_anomalies(*period).loc[period[0]:period[1] - 1]
    forcing = list(zip(anom["dt_c"], anom["p_ratio"]))
    return calibrate_temperature(data.surface, data.mask, climate, target, yearly_forcing=forcing), target, period


def thinning_rates(data: SiteData, result: RunResult) -> pd.DataFrame:
    """Observed vs modelled mean thinning rate (m/yr) between consecutive DEMs, on cells both DEMs cover."""
    start = data.site.start_year
    years = sorted(y for y in data.observed if start <= y <= start + result.scenario.years)
    snap = {int(round(y)): s for y, s in zip(result.snapshot_years, result.snapshots)}

    def modelled_surface(year):
        return data.bed + snap[year - start]

    rows = []
    pairs = list(zip(years[:-1], years[1:])) + ([(years[0], years[-1])] if len(years) > 2 else [])
    for a, b in pairs:
        obs_a, obs_b = data.observed[a], data.observed[b]
        valid = data.mask & np.isfinite(obs_a) & np.isfinite(obs_b)
        rows.append({
            "period": f"{a}-{b}",
            "observed_m_per_yr": float(np.mean(obs_b[valid] - obs_a[valid]) / (b - a)),
            "modeled_m_per_yr": float(np.mean(modelled_surface(b)[valid] - modelled_surface(a)[valid]) / (b - a)),
            "cells": int(valid.sum()),
        })
    return pd.DataFrame(rows)


def run_history(data: SiteData, record: ClimateRecord, flow: FlowParams = FlowParams(),
                base: ClimateParams | None = None, end_year: int | None = None, progress=None) -> HistoryRun:
    climate, target, period = calibrate(data, record, base)
    start = data.site.start_year
    end = (end_year or record.last_year) + 1  # replay through the end of the last complete year
    scenario = historical_scenario(record, start, end, period)
    result = simulate(data.bed, data.thickness, data.grid.dx, climate, scenario, flow,
                      accumulation_mask=data.mask, ice_domain=data.ice_domain, snapshot_every=1,
                      progress=progress)

    snap = {int(round(y)): s for y, s in zip(result.snapshot_years, result.snapshots)}
    comparisons = {year: band_comparison(data, data.bed + snap[year - start], year)
                   for year in sorted(data.observed) if start < year <= end}

    recent = record.annual_anomalies(*period).loc[end - RECENT_YEARS:end - 1, "dt_c"].mean()
    present_climate = climate.with_changes(
        t_annual_ref=climate.t_annual_ref + float(recent),
        source=f"{climate.source}, shifted by the {end - RECENT_YEARS}-{end - 1} temperature anomaly",
    )
    return HistoryRun(climate=climate, calibration_period=period, target_rate=target, result=result,
                      comparisons=comparisons, rates=thinning_rates(data, result), present_year=end - 1,
                      present_thickness=result.final_thickness, present_climate=present_climate,
                      recent_warming=float(recent))


def prepare_history(data: SiteData, record: ClimateRecord, flow: FlowParams = FlowParams(),
                    base: ClimateParams | None = None) -> HistoryRun:
    """``run_history`` with a disk cache, so the app starts instantly after the first run."""
    record_id = hashlib.sha1(pd.util.hash_pandas_object(record.data).to_numpy().tobytes()).hexdigest()
    key = (data.site.name, data.grid.dx, record.name, record_id, tuple(record.monthly_lapse), flow, base)
    return cached("history", key, lambda: run_history(data, record, flow, base=base))
