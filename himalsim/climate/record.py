"""A monthly climate record at a known elevation, with the helpers the glacier model needs."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ClimateRecord:
    """Monthly mean air temperature (°C) and precipitation total (mm) at ``elevation``.

    ``data`` has a monthly DatetimeIndex (month start) and columns ``t_c`` and ``p_mm``.
    ``sources`` lists where every number came from. Keep it accurate: students will read it.
    """

    name: str
    elevation: float
    data: pd.DataFrame
    sources: list[str] = field(default_factory=list)

    @property
    def first_year(self) -> int:
        return int(self.data.index.year.min())

    @property
    def last_year(self) -> int:
        """Last calendar year with all 12 months present."""
        counts = self.data.dropna().groupby(self.data.dropna().index.year).size()
        return int(counts[counts == 12].index.max())

    def period(self, start: int, end: int) -> pd.DataFrame:
        return self.data.loc[f"{start}-01-01":f"{end}-12-31"]

    def climatology(self, start: int, end: int) -> pd.DataFrame:
        """Average of each calendar month over ``start``-``end`` (12 rows, index 1-12)."""
        d = self.period(start, end)
        return d.groupby(d.index.month).mean()

    def annual(self) -> pd.DataFrame:
        """Calendar-year mean temperature and total precipitation (complete years only)."""
        d = self.data.dropna()
        g = d.groupby(d.index.year)
        out = pd.DataFrame({"t_c": g["t_c"].mean(), "p_mm": g["p_mm"].sum(), "months": g.size()})
        return out[out["months"] == 12].drop(columns="months")

    def annual_anomalies(self, base_start: int, base_end: int) -> pd.DataFrame:
        """Per-year temperature anomaly (°C) and precipitation ratio relative to a base period."""
        ann = self.annual()
        base = ann.loc[base_start:base_end]
        return pd.DataFrame({"dt_c": ann["t_c"] - base["t_c"].mean(), "p_ratio": ann["p_mm"] / base["p_mm"].mean()})

    def trend(self, start: int, end: int) -> float:
        """Linear temperature trend in °C per decade."""
        ann = self.annual().loc[start:end]
        return float(np.polyfit(ann.index.values, ann["t_c"].values, 1)[0] * 10.0)

    def with_precip_scaled(self, annual_mm: float, start: int, end: int, note: str) -> ClimateRecord:
        """Rescale precipitation so its ``start``-``end`` annual mean equals ``annual_mm``.

        Keeps the month-to-month and year-to-year *pattern* of the record but fixes its *level*,
        the standard way to correct a reanalysis with a station measurement.
        """
        current = self.annual().loc[start:end, "p_mm"].mean()
        data = self.data.copy()
        data["p_mm"] = data["p_mm"] * annual_mm / current
        return ClimateRecord(self.name, self.elevation, data, self.sources + [note])
