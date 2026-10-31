"""ICIMOD automatic weather stations (AWS) in the Langtang valley: hourly downloads -> checked monthly values.

Three stations climb from the valley floor onto Yala Glacier:
  * Kyanjing, 3862 m, grassland in the village (2012-2019), doi:10.26066/RDS.22464.
  * Yala Base Camp, 5090 m, on rock beside the glacier (2012-2019; destroyed by the Gorkha earthquake on
    25 Apr 2015 and rebuilt), doi:10.26066/RDS.26859.
  * Yala Glacier, on the ice: 5291 m from May 2016, moved up to 5330 m on 28 Nov 2018, doi:10.26066/RDS.1972507.

The downloads are free from the ICIMOD Regional Database System after registering, but they are not
redistributed with HimSim (git-ignored): the 2016 terms inside the Kyanjing and Base Camp downloads forbid
copying without ICIMOD's consent, although the dataset pages now list CC BY 4.0. Until that is settled, only
statistics computed from them are shown. Each file's path can be overridden with an environment variable.

All three exports share one layout: ``DATE`` + ``TIME`` columns (Nepal time), NA for missing, one row per
hour labelled with the hour's *end*. Known faults are listed per station in ``bad_periods`` and removed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from himsim.climate.record import ClimateRecord

REPO_ROOT = Path(__file__).resolve().parents[2]

MIN_COVERAGE = 0.8  # a month needs 80 % of its hours (or days) to count; gaps are never filled in
BUCKET_EMPTIED_MM = -20.0  # an hourly drop this large in the gauge bucket means it was emptied, not evaporation
GAUGE_DRY_MM = 10.0  # months where both precipitation estimates are below this count as dry and agree
GAUGE_AGREEMENT = 2.0  # otherwise the two estimates must agree within this factor


@dataclass(frozen=True)
class AwsStation:
    name: str
    folder: str  # download folder, relative to the repository
    filename: str  # the hourly CSV inside ``<folder>/data``
    env_var: str  # environment variable that overrides the file path
    elevation: float  # m, as given in the station-detail sheet
    lat: float
    lon: float
    surface: str  # what the station stands on
    citation: str
    moves: tuple[tuple[str, float], ...] = ()  # (date, new elevation) when the station was moved
    bad_periods: tuple[tuple[str, str, str], ...] = ()  # (start, end, why): every reading in [start, end) removed

    @property
    def path(self) -> Path:
        return Path(os.environ.get(self.env_var, REPO_ROOT / self.folder / "data" / self.filename))

    def available(self) -> bool:
        return self.path.is_file()

    def elevation_on(self, when) -> float:
        z = self.elevation
        for date, new in self.moves:
            if pd.Timestamp(when) >= pd.Timestamp(date):
                z = new
        return z


KYANJING = AwsStation(
    name="Kyanjing", folder="Meteorological data from Kyanging automatic weather station",
    filename="AWSKyangjin.csv", env_var="HIMSIM_KYANJING_AWS", elevation=3862.0,
    # ICIMOD metadata record dcab6bc7-9dd0-4686-86ce-70664c8589ab. The station-detail sheet gives 85.68619 E,
    # which would put the station 12 km up-valley; we take it as a typo.
    lat=28.21081, lon=85.56169, surface="grassland",
    citation="ICIMOD (2016). Meteorological data from Kyanging automatic weather station [Data set]. ICIMOD. "
             "doi:10.26066/RDS.22464",
)
YALA_BASE_CAMP = AwsStation(
    name="Yala Base Camp", folder="Meteorological data from Yala Base Camp automatic weather station",
    filename="AWSYalaBC.csv", env_var="HIMSIM_YALA_BC_AWS", elevation=5090.0,
    lat=28.2323, lon=85.60967, surface="rock",  # station-detail sheet (the metadata XML says 28.23252 N 85.61208 E)
    citation="ICIMOD (2016). Meteorological data from Yala Base Camp automatic weather station [Data set]. ICIMOD. "
             "doi:10.26066/RDS.26859",
    bad_periods=(
        ("2016-06-13", "2016-06-14", "temperature jumps from 3 to 26 degC within an hour while RH sticks at 100 %"),
        ("2016-06-17", "2016-06-18", "the same fault again (hourly temperatures above 25 degC at 5090 m)"),
        ("2014-09-30", "2014-10-20", "precipitation flagged unreliable in the station-detail sheet"),
        ("2018-09-13", "2018-10-10", "precipitation flagged unreliable in the station-detail sheet"),
        ("2019-09-25", "2019-10-25", "precipitation flagged unreliable in the station-detail sheet"),
        ("2019-11-18 18:00", "2020-01-01", "columns stored in a different order from here on (temperature under PVOL)"),
    ),
)
YALA_GLACIER = AwsStation(
    name="Yala Glacier", folder="AWS Yala Glacier", filename="AWSYalaGlacier.csv", env_var="HIMSIM_YALA_GLACIER_AWS",
    elevation=5291.0, lat=28.23463, lon=85.61797, surface="ice",
    citation="ICIMOD (2021). AWS Yala Glacier [Data set]. ICIMOD. doi:10.26066/RDS.1972507",
    moves=(("2018-11-28", 5330.0),),  # fell over in 2018; reinstalled slightly higher (28.23437 N, 85.62083 E)
)
STATIONS = (KYANJING, YALA_BASE_CAMP, YALA_GLACIER)


def read_aws(path: str | Path) -> pd.DataFrame:
    """An hourly ICIMOD export, indexed by the middle of each hour (Nepal time, UTC+5:45).

    Each row summarises the 10-minute readings *ending* at its timestamp, so 16:00 is 15:00-16:00.
    Kyanjing mixes ``m/d/Y`` + ``H:MM:SS`` and ``m/d/Y `` + ``H:MM`` (from 2018); both are handled.
    """
    raw = pd.read_csv(path, na_values=["NA"], low_memory=False)
    date = pd.to_datetime(raw["DATE"].str.strip(), format="%m/%d/%Y")
    hm = raw["TIME"].str.strip().str.split(":", expand=True).iloc[:, :2].astype(int)
    end = date + pd.to_timedelta(hm[0], unit="h") + pd.to_timedelta(hm[1], unit="m")
    data = raw.drop(columns=["DATE", "TIME"]).apply(pd.to_numeric, errors="coerce")
    data.index = pd.DatetimeIndex(end - pd.Timedelta(minutes=30), name="time")
    return data


def remove_bad_periods(hourly: pd.DataFrame, station: AwsStation) -> pd.DataFrame:
    """Blank the station's known faults. Precipitation-only faults blank only the gauge columns."""
    out = hourly.copy()
    gauge = [c for c in ("PVOL", "BCON") if c in out]
    for start, end, why in station.bad_periods:
        rows = (out.index >= pd.Timestamp(start)) & (out.index < pd.Timestamp(end))
        out.loc[rows, gauge if why.startswith("precipitation") else out.columns] = float("nan")
    return out


def _bucket_precip_daily(bucket: pd.Series) -> pd.Series:
    """Daily precipitation from the weight of the gauge's bucket (mm).

    The bucket only fills, except when it is emptied (a sudden large drop, removed here) and
    through slow evaporation and wind noise, which mostly cancel within a day. A day needs 18 of
    its 24 hourly changes.
    """
    change = bucket.diff()
    change[change < BUCKET_EMPTIED_MM] = 0.0
    daily = change.resample("D").sum(min_count=1)
    return daily.clip(lower=0.0).where(change.resample("D").count() >= 18)


def aws_monthly(hourly: pd.DataFrame) -> pd.DataFrame:
    """Monthly temperature and precipitation from the hourly AWS data, with quality control.

    * ``t_c``: mean of the hourly air temperatures (``TAIR``), if >= 80 % of the hours exist.
    * ``p_gauge_mm``: the gauge's own precipitation (``PVOL``, hourly sums).
    * ``p_bucket_mm``: the gain in bucket weight (``BCON``), an independent check on the same gauge.
    * ``p_mm``: ``p_gauge_mm`` where both estimates agree, else empty. At Kyanjing they don't agree
      for long stretches: PVOL reads 0 mm through the 2015 and 2016 monsoons while the bucket fills,
      and in 2018-2019 it is about one fifth of the bucket gain (probably hourly means stored instead
      of sums). Stations without a gauge (Yala Glacier) get empty precipitation.
    """
    months = hourly.resample("MS")
    hours = months.size().index.days_in_month * 24
    t_ok = months["TAIR"].count().to_numpy() >= MIN_COVERAGE * hours
    out = pd.DataFrame({"t_c": months["TAIR"].mean().where(t_ok)})
    if {"PVOL", "BCON"} <= set(hourly.columns):
        p_ok = months["PVOL"].count().to_numpy() >= MIN_COVERAGE * hours
        daily = _bucket_precip_daily(hourly["BCON"]).resample("MS")
        b_ok = daily.count().to_numpy() >= MIN_COVERAGE * daily.size().index.days_in_month
        out["p_gauge_mm"] = months["PVOL"].sum().where(p_ok)
        out["p_bucket_mm"] = daily.sum().where(b_ok)
        g, b = out["p_gauge_mm"], out["p_bucket_mm"]
        dry = (g < GAUGE_DRY_MM) & (b < GAUGE_DRY_MM)
        ratio = g / b.where(b > 0)
        out["p_mm"] = g.where(dry | ((ratio >= 1.0 / GAUGE_AGREEMENT) & (ratio <= GAUGE_AGREEMENT)))
    else:
        out["p_gauge_mm"] = out["p_bucket_mm"] = out["p_mm"] = float("nan")
    out.index.name = "month"
    return out


def load_aws(station: AwsStation, path: str | Path | None = None) -> ClimateRecord:
    """A station as a monthly ClimateRecord. ``data["z_m"]`` is the station height in each month."""
    monthly = aws_monthly(remove_bad_periods(read_aws(path or station.path), station))
    data = monthly[["t_c", "p_mm"]].copy()
    data["z_m"] = [station.elevation_on(m) for m in data.index]
    return ClimateRecord(
        name=f"{station.name} weather station (ICIMOD)",
        elevation=station.elevation,
        data=data,
        sources=[station.citation,
                 f"Months need {MIN_COVERAGE:.0%} of their hourly records; precipitation only where the gauge reading "
                 f"and its bucket weight agree within a factor of {GAUGE_AGREEMENT:g}"],
    )


def lapse_rates(low: ClimateRecord, high: ClimateRecord) -> pd.DataFrame:
    """How fast the air cools with height between two stations, for every month both measured.

    ``lapse_c_per_km`` is positive when the higher station is colder, matching the model's ``lapse_rate``.
    """
    j = pd.DataFrame({"t_low": low.data["t_c"], "t_high": high.data["t_c"],
                      "z_low": low.data["z_m"], "z_high": high.data["z_m"]}).dropna()
    j["lapse_c_per_km"] = (j["t_low"] - j["t_high"]) / (j["z_high"] - j["z_low"]) * 1000.0
    return j


ICE_ALBEDO_LIMIT = 0.4  # days darker than this count as bare ice (the split used by Litt et al. 2019)


def _daily_mean(s: pd.Series) -> pd.Series:
    return s.resample("D").mean().where(s.resample("D").count() >= 20)


def radiation_inputs(glacier: AwsStation = YALA_GLACIER, off_ice: AwsStation = YALA_BASE_CAMP) -> dict:
    """The sunshine and temperature-spread inputs of the "eti" melt rule, measured at the Yala stations.

    * ``sw_in``: monthly mean incoming shortwave radiation (W m-2, Jan first), complete months only,
      averaged over the years (days need 20 of 24 hours).
    * ``albedo_ice`` / ``albedo_snow``: median daily albedo (reflected / incoming shortwave, days with
      more than 50 W m-2 coming in) below / at or above ``ICE_ALBEDO_LIMIT``; values above 1 (snow on
      the upward-looking sensor) are dropped.
    * ``daily_t_sd``: standard deviation of daily mean air temperature around its own monthly mean,
      by calendar month, at the off-ice station.
    """
    g = remove_bad_periods(read_aws(glacier.path), glacier)
    sw = _daily_mean(g["KINC"].clip(lower=0.0))
    months = sw.resample("MS")
    complete = months.count() >= MIN_COVERAGE * months.size().index.days_in_month
    monthly = months.mean().where(complete.to_numpy())
    albedo = (_daily_mean(g["KOUT"].clip(lower=0.0)) / sw).where(sw > 50.0)
    albedo = albedo[albedo <= 1.0]

    t = _daily_mean(remove_bad_periods(read_aws(off_ice.path), off_ice)["TAIR"])
    anomaly = t - t.groupby([t.index.year, t.index.month]).transform("mean")
    return {
        "sw_in": tuple(round(float(v), 1) for v in monthly.groupby(monthly.index.month).mean()),
        "albedo_ice": round(float(albedo[albedo < ICE_ALBEDO_LIMIT].median()), 2),
        "albedo_snow": round(float(albedo[albedo >= ICE_ALBEDO_LIMIT].median()), 2),
        "daily_t_sd": tuple(round(float(v), 2) for v in anomaly.groupby(anomaly.index.month).std()),
    }
