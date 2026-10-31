"""Kyanjin Gompa, Langtang valley (3862 m): the reference climate for Yala Glacier.

What we know from measurements:
  * Nepal's Department of Hydrology and Meteorology (DHM) has run a station at Kyanjing
    (3862 m) since 1987. An automatic weather station there is co-run by DHM, ICIMOD and
    Utrecht University (Steiner et al. 2021, doi:10.1002/hyp.14189).
  * Station precipitation: 867 mm per year at 3857 m (Immerzeel et al. 2014), with 70-90 %
    falling in the monsoon.
  * The station data are open on the ICIMOD Regional Database System after a free
    registration: Kyanjing AWS doi:10.26066/RDS.22464 (hourly, 22 Mar 2012 - 31 Dec 2019).
    ``load_kyanjing_aws`` reads that download (via ``icimod_aws``). The raw file is not redistributed
    with HimSim; only twelve statistics computed from it are (``AWS_MINUS_ERA5LAND``).

What the model uses (``load_record``):
  * Temperature: ERA5-Land, adjusted to 3862 m by Open-Meteo, with its average seasonal cycle
    corrected to the AWS: each calendar month gets the mean station-minus-ERA5-Land difference of
    2012-2019. ERA5-Land's winters are 2-3 degC too cold here and its monsoon months slightly too warm.
    Year-to-year changes and the trend stay ERA5-Land's.
  * Cooling with height: a measured lapse rate for each calendar month, from the Kyanjing and Yala Base
    Camp (5090 m) stations (``KYANJIN_TO_BASE_CAMP_LAPSE``): 4.9 degC/km in July up to 7.0 in March, 5.7
    on average. Above Base Camp the same rates are assumed (the Yala Glacier station is on the ice, whose
    chilled boundary layer is a different thing).
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

from himsim.climate.icimod_aws import KYANJING, YALA_BASE_CAMP, load_aws
from himsim.climate.openmeteo import daily_to_monthly, fetch_daily
from himsim.climate.record import ClimateRecord

DATA_FILE = Path(__file__).resolve().parent / "data" / "kyanjin_monthly.csv"
AWS_CITATION = KYANJING.citation


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

# Kyanjing AWS minus ERA5-Land (degC) per calendar month (Jan first): the mean over the 72 months 2012-04 to
# 2019-12 in which the station measured >= 80 % of the hours; AWS_OFFSET_YEARS = how many years each mean uses.
# Computed by ``station_temperature_offsets`` (scripts/kyanjing_offsets.py); a test re-checks them against the file.
AWS_MINUS_ERA5LAND = (2.25, 2.76, 2.78, 1.94, 0.97, -0.05, -0.41, -0.38, 0.0, 0.74, 1.76, 1.78)
AWS_OFFSET_YEARS = (5, 5, 4, 4, 7, 7, 6, 6, 6, 6, 8, 8)

# How fast the air cools with height (degC per km) in each calendar month (Jan first), Kyanjing (3862 m) ->
# Yala Base Camp (5090 m): the mean over the 63 months 2012-2019 that both stations measured fully;
# LAPSE_YEARS = how many years each mean uses (year-to-year spread 0.13-0.24 degC/km in Jun-Sep, <= 0.64 otherwise).
# Computed by ``icimod_aws.lapse_rates`` (scripts/kyanjing_offsets.py); a test re-checks them against the files.
KYANJIN_TO_BASE_CAMP_LAPSE = (6.05, 6.79, 6.99, 6.68, 6.27, 5.3, 4.87, 5.07, 5.22, 5.37, 5.65, 5.51)
LAPSE_YEARS = (5, 4, 3, 3, 6, 7, 6, 6, 6, 5, 7, 5)


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


def load_record(scale_precip_to_station: bool = True, correct_seasons_to_station: bool = True,
                measured_lapse_rates: bool = True) -> ClimateRecord:
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
    if correct_seasons_to_station:
        record = record.with_temperature_offsets(
            AWS_MINUS_ERA5LAND,
            f"Temperature: each calendar month shifted by the mean Kyanjing AWS minus ERA5-Land difference over "
            f"{sum(AWS_OFFSET_YEARS)} station months, 2012-2019 ({KYANJING.citation})")
        record.name = "Kyanjin (ERA5-Land temperature corrected to the Kyanjing station, ERA5 precipitation)"
    if measured_lapse_rates:
        record = record.with_monthly_lapse(
            [v / 1000.0 for v in KYANJIN_TO_BASE_CAMP_LAPSE],
            f"Cooling with height: measured for each calendar month between the Kyanjing (3862 m) and Yala Base Camp "
            f"(5090 m) stations over {sum(LAPSE_YEARS)} months, 2012-2019 ({KYANJING.citation}; {YALA_BASE_CAMP.citation})")
    return record


def station_temperature_offsets(station: ClimateRecord, reanalysis: ClimateRecord) -> pd.DataFrame:
    """Mean station-minus-reanalysis temperature for each calendar month (rows 1-12), with the years used."""
    diff = (station.data["t_c"] - reanalysis.data["t_c"].reindex(station.data.index)).dropna()
    g = diff.groupby(diff.index.month)
    return pd.DataFrame({"offset_c": g.mean(), "years": g.size()}).reindex(range(1, 13))


def load_kyanjing_aws(path: str | Path | None = None) -> ClimateRecord:
    """The Kyanjing AWS as a monthly ClimateRecord (quality-controlled, see ``icimod_aws.aws_monthly``)."""
    return load_aws(KYANJING, path)


def aws_available() -> bool:
    return KYANJING.available()
