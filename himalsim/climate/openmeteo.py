"""Download reanalysis climate from the Open-Meteo historical archive (free, no API key).

Open-Meteo serves ECMWF reanalyses (ERA5 from 1940, ERA5-Land from 1950). Passing the
station ``elevation`` makes Open-Meteo adjust temperature from the model-grid height to
that elevation. Data licence: CC BY 4.0 (Open-Meteo), contains modified Copernicus Climate
Change Service information. Free use is for non-commercial purposes.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

import pandas as pd

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_daily(lat: float, lon: float, elevation: float, start: str, end: str, model: str = "era5_land",
                variables: tuple[str, ...] = ("temperature_2m_mean", "precipitation_sum"),
                timeout: float = 300.0) -> tuple[pd.DataFrame, dict]:
    """Daily series for one point. Returns ``(frame, metadata)``; metadata includes the grid cell used."""
    query = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "elevation": elevation, "start_date": start, "end_date": end,
        "daily": ",".join(variables), "models": model, "timezone": "Asia/Kathmandu",
    })
    with urllib.request.urlopen(f"{ARCHIVE_URL}?{query}", timeout=timeout) as resp:
        payload = json.load(resp)
    if "daily" not in payload:
        raise RuntimeError(f"Open-Meteo error: {payload}")
    frame = pd.DataFrame(payload["daily"])
    frame["time"] = pd.to_datetime(frame["time"])
    meta = {k: payload[k] for k in ("latitude", "longitude", "elevation")}
    meta["model"] = model
    return frame.set_index("time"), meta


def daily_to_monthly(daily: pd.DataFrame, t_col: str = "temperature_2m_mean", p_col: str = "precipitation_sum",
                     min_days: int = 25) -> pd.DataFrame:
    """Monthly mean temperature and precipitation total; months with fewer than ``min_days`` valid days are NaN."""
    out = pd.DataFrame(index=daily.resample("MS").mean().index)
    if t_col in daily:
        t = daily[t_col].resample("MS")
        out["t_c"] = t.mean().where(t.count() >= min_days)
    if p_col in daily:
        p = daily[p_col].resample("MS")
        out["p_mm"] = p.sum().where(p.count() >= min_days)
    return out
