"""Kyanjin Gompa, Langtang valley (3862 m): the reference climate for Yala Glacier.

What we know from measurements:
  * Nepal's Department of Hydrology and Meteorology (DHM) has run a station at Kyanjing
    (3862 m) since 1987. An automatic weather station there is co-run by DHM, ICIMOD and
    Utrecht University (Steiner et al. 2021, doi:10.1002/hyp.14189).
  * Station precipitation: 867 mm per year at 3857 m (Immerzeel et al. 2014), with 70-90 %
    falling in the monsoon.
  * The station data are open on the ICIMOD Regional Database System after a free
    registration: Kyanjing AWS doi:10.26066/RDS.22464. ``load_icimod_csv`` reads such a download.

What we use until then (``load_record``):
  * Temperature: ERA5-Land, adjusted to 3862 m by Open-Meteo.
  * Precipitation: ERA5 month-to-month and year-to-year pattern, rescaled so that the
    1981-2010 mean equals the station's 867 mm. ERA5 alone gives ~1800 mm at Kyanjin,
    about twice what the gauge measures.
The record is stored in ``data/kyanjin_monthly.csv`` and rebuilt with
``scripts/fetch_kyanjin_climate.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from himsim.climate.openmeteo import daily_to_monthly, fetch_daily
from himsim.climate.record import ClimateRecord

DATA_FILE = Path(__file__).resolve().parent / "data" / "kyanjin_monthly.csv"


@dataclass(frozen=True)
class Station:
    name: str
    lat: float
    lon: float
    elevation: float
    annual_precip_mm: float
    annual_precip_source: str
    monsoon_share_range: tuple[float, float]
    data_doi: str


KYANJIN = Station(
    name="Kyanjin Gompa (Kyanjing)",
    lat=28.2113,  # village location; station coordinates are not published in Steiner et al. (2021)
    lon=85.5627,
    elevation=3862.0,
    annual_precip_mm=867.0,
    annual_precip_source="Immerzeel et al. (2014), gauge at 3857 m, as cited in Steiner et al. (2021, Hydrol. Process.)",
    monsoon_share_range=(0.70, 0.90),
    data_doi="10.26066/RDS.22464",
)

PRECIP_SCALING_PERIOD = (1981, 2010)


def build_monthly(start: str = "1960-01-01", end: str = "2025-12-31") -> tuple[pd.DataFrame, list[dict]]:
    """Download the raw monthly series (both reanalyses) for Kyanjin. Needs internet."""
    s = KYANJIN
    land, meta_land = fetch_daily(s.lat, s.lon, s.elevation, start, end, model="era5_land",
                                  variables=("temperature_2m_mean",))
    era5, meta_era5 = fetch_daily(s.lat, s.lon, s.elevation, start, end, model="era5")
    m_land, m_era5 = daily_to_monthly(land), daily_to_monthly(era5)
    frame = pd.DataFrame({
        "t_era5land_c": m_land["t_c"].round(2),
        "t_era5_c": m_era5["t_c"].round(2),
        "p_era5_mm": m_era5["p_mm"].round(1),
    })
    frame.index.name = "month"
    return frame, [meta_land, meta_era5]


def load_record(scale_precip_to_station: bool = True) -> ClimateRecord:
    """The Kyanjin reference record used by the model (see module docstring)."""
    raw = pd.read_csv(DATA_FILE, comment="#", parse_dates=["month"], index_col="month")
    record = ClimateRecord(
        name="Kyanjin (ERA5-Land temperature, ERA5 precipitation)",
        elevation=KYANJIN.elevation,
        data=pd.DataFrame({"t_c": raw["t_era5land_c"], "p_mm": raw["p_era5_mm"]}),
        sources=[
            "Temperature: ERA5-Land (Muñoz-Sabater et al. 2021) via Open-Meteo, adjusted to 3862 m",
            "Precipitation pattern: ERA5 (Hersbach et al. 2020) via Open-Meteo",
        ],
    )
    if scale_precip_to_station:
        a, b = PRECIP_SCALING_PERIOD
        record = record.with_precip_scaled(
            KYANJIN.annual_precip_mm, a, b,
            f"Precipitation rescaled so the {a}-{b} mean equals {KYANJIN.annual_precip_mm:.0f} mm/yr "
            f"({KYANJIN.annual_precip_source})")
    return record


def load_icimod_csv(path: str | Path, time_col: str, temp_col: str, precip_col: str,
                    name: str = "Kyanjing AWS (ICIMOD)") -> ClimateRecord:
    """Read a station file downloaded from the ICIMOD Regional Database System.

    Column names differ between station exports, so pass them explicitly after opening the
    file once. Sub-daily values are averaged (temperature) or summed (precipitation) to months.
    Months with less than 80 % of their records are left empty rather than guessed.
    """
    raw = pd.read_csv(path, parse_dates=[time_col], index_col=time_col)
    raw = raw[[temp_col, precip_col]].apply(pd.to_numeric, errors="coerce")
    per_month = raw.resample("MS")
    expected = raw.resample("MS").size().max()
    t = per_month[temp_col].mean().where(per_month[temp_col].count() >= 0.8 * expected)
    p = per_month[precip_col].sum().where(per_month[precip_col].count() >= 0.8 * expected)
    return ClimateRecord(name, KYANJIN.elevation, pd.DataFrame({"t_c": t, "p_mm": p}),
                         [f"ICIMOD Regional Database System, doi:{KYANJIN.data_doi}"])
