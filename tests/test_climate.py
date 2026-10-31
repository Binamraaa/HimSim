import numpy as np
import pandas as pd
import pytest

from himsim.climate.icimod_aws import STATIONS
from himsim.climate.kyanjin import KYANJIN, load_record
from himsim.climate.record import ClimateRecord
from himsim.glacier.climate import ClimateParams
from himsim.glacier.history import historical_scenario

_HAVE_YALA_AWS = all(s.available() for s in STATIONS)


def _synthetic_record(years=range(2000, 2010)):
    idx = pd.date_range(f"{min(years)}-01-01", f"{max(years)}-12-01", freq="MS")
    t = 5 + 8 * np.cos(2 * np.pi * (idx.month - 7) / 12) + 0.1 * (idx.year - min(years))
    p = np.where(idx.month.isin([6, 7, 8, 9]), 150.0, 20.0)
    return ClimateRecord("synthetic", 4000.0, pd.DataFrame({"t_c": t, "p_mm": p}, index=idx))


def test_annual_anomalies_average_to_zero_over_base():
    r = _synthetic_record()
    a = r.annual_anomalies(2000, 2009)
    assert a["dt_c"].mean() == pytest.approx(0.0, abs=1e-9)
    assert a["p_ratio"].mean() == pytest.approx(1.0)
    assert r.trend(2000, 2009) == pytest.approx(1.0, rel=1e-6)  # 0.1 °C/yr


def test_precip_scaling_keeps_pattern():
    r = _synthetic_record()
    s = r.with_precip_scaled(500.0, 2000, 2009, "test")
    assert s.annual().loc[2000:2009, "p_mm"].mean() == pytest.approx(500.0)
    ratio = s.data["p_mm"] / r.data["p_mm"]
    assert ratio.std() < 1e-12


def test_temperature_offsets_fix_seasons_but_keep_anomalies():
    r = _synthetic_record()
    offsets = np.linspace(2.0, -1.0, 12)
    c = r.with_temperature_offsets(offsets, "test")
    np.testing.assert_allclose(c.climatology(2000, 2009)["t_c"] - r.climatology(2000, 2009)["t_c"], offsets)
    pd.testing.assert_frame_equal(c.annual_anomalies(2000, 2009), r.annual_anomalies(2000, 2009))
    assert c.trend(2000, 2009) == pytest.approx(r.trend(2000, 2009))
    assert c.data["p_mm"].equals(r.data["p_mm"])


def test_measured_monthly_lapse_rates():
    r = _synthetic_record().with_monthly_lapse(np.linspace(0.005, 0.007, 12), "test")
    c = ClimateParams.from_record(r, 2000, 2009)
    assert c.lapse_rate == pytest.approx(0.006)
    t0, t1 = c.monthly_temperature(np.array(4000.0)), c.monthly_temperature(np.array(5000.0))
    np.testing.assert_allclose(t0 - t1, np.linspace(5.0, 7.0, 12))  # each month cools at its own rate
    scaled = ClimateParams.from_record(r, 2000, 2009, lapse_rate=0.0075)  # e.g. the teacher slider
    np.testing.assert_allclose(np.asarray(scaled.monthly_lapse) / np.asarray(c.monthly_lapse), 1.25)
    plain = ClimateParams.from_record(_synthetic_record(), 2000, 2009, lapse_rate=0.0065)
    assert plain.monthly_lapse == () and plain.lapse_rate == 0.0065


def test_climate_params_from_record():
    r = _synthetic_record()
    c = ClimateParams.from_record(r, 2000, 2009)
    assert sum(c.precip_share) == pytest.approx(1.0)
    assert sum(c.seasonal_t) == pytest.approx(0.0, abs=1e-9)
    t = c.monthly_temperature(np.array(4000.0))
    assert t.mean() == pytest.approx(r.climatology(2000, 2009)["t_c"].mean())


def test_historical_scenario_replays_years():
    r = _synthetic_record()
    s = historical_scenario(r, 2002, 2006, (2000, 2009))
    anom = r.annual_anomalies(2000, 2009)
    assert s.years == 4 and len(s.t_anomalies) == 4
    assert s.temp_delta(0.5) == pytest.approx(anom.loc[2002, "dt_c"])
    assert s.temp_delta(3.9) == pytest.approx(anom.loc[2005, "dt_c"])


def test_kyanjin_record_matches_station_facts():
    r = load_record()
    clim = r.climatology(1981, 2010)
    assert clim["p_mm"].sum() == pytest.approx(KYANJIN.annual_precip_mm, rel=1e-6)
    share = clim["p_mm"].loc[[6, 7, 8, 9]].sum() / clim["p_mm"].sum()
    assert KYANJIN.monsoon_share_range[0] <= share <= KYANJIN.monsoon_share_range[1]
    assert clim["t_c"].idxmax() in (7, 8) and clim["t_c"].idxmin() in (1, 2)
    assert r.last_year >= 2025


def _write_aws_csv(path):
    """Two months of hourly AWS rows in both of the export's timestamp styles."""
    idx = pd.date_range("2013-07-01 01:00", "2013-09-01 00:00", freq="h")
    rows = pd.DataFrame({"TAIR": 10.0, "PVOL": 0.1, "BCON": 100.0 + 0.1 * np.arange(len(idx))}, index=idx)
    rows.loc["2013-07-20 12:00", "BCON"] = np.nan  # a missing reading
    rows.loc["2013-07-25 12:00":, "BCON"] -= 300.0  # bucket emptied: must not count as negative rain
    rows.loc["2013-08-01 01:00":, "PVOL"] = 0.0  # August: the gauge reads zero while the bucket fills
    rows.loc["2013-08-01 01:00":"2013-08-10 00:00", "TAIR"] = np.nan  # 9 days missing: < 80 % of hours
    old = idx < "2013-08-01"
    out = pd.DataFrame({
        "DATE": np.where(old, idx.strftime("%m/%d/%Y").str.lstrip("0"), idx.strftime("%m/%d/%Y ").str.lstrip("0")),
        "TIME": np.where(old, [f"{t.hour}:00:00" for t in idx], [f"{t.hour}:00" for t in idx]),
    })
    out = pd.concat([out, rows.reset_index(drop=True)], axis=1)
    out.to_csv(path, index=False, na_rep="NA")


def test_aws_reader_quality_control(tmp_path):
    from himsim.climate.icimod_aws import aws_monthly, read_aws

    f = tmp_path / "aws.csv"
    _write_aws_csv(f)
    hourly = read_aws(f)
    assert hourly.index[0] == pd.Timestamp("2013-07-01 00:30")  # middle of the hour ending 01:00
    m = aws_monthly(hourly)
    jul, aug = m.loc["2013-07-01"], m.loc["2013-08-01"]
    assert jul["t_c"] == pytest.approx(10.0)
    assert np.isnan(aug["t_c"])  # too many missing hours
    assert jul["p_gauge_mm"] == pytest.approx(744 * 0.1, rel=0.01)
    assert jul["p_bucket_mm"] == pytest.approx(744 * 0.1, rel=0.02)  # emptying ignored
    assert jul["p_mm"] == pytest.approx(jul["p_gauge_mm"])  # the two agree
    assert aug["p_gauge_mm"] == 0.0 and aug["p_bucket_mm"] > 50
    assert np.isnan(aug["p_mm"])  # they disagree, so August precipitation is not trusted


@pytest.mark.skipif(not __import__("himsim.climate.kyanjin", fromlist=["aws_available"]).aws_available(),
                    reason="Kyanjing AWS download not present")
def test_kyanjing_aws_matches_known_facts():
    """The real ICIMOD file: coverage, known gauge failures, and the reanalysis cold bias."""
    from himsim.climate.kyanjin import load_kyanjing_aws

    aws = load_kyanjing_aws()
    t, p = aws.data["t_c"].dropna(), aws.data["p_mm"]
    assert t.index.min() == pd.Timestamp("2012-04-01") and t.index.max() == pd.Timestamp("2019-12-01")
    assert len(t) == 72
    assert p.loc["2016-06":"2016-09"].isna().all()  # gauge read 0 mm through the 2016 monsoon
    assert p.loc["2018-06":"2018-09"].isna().all()  # gauge ~1/5 of the bucket gain in 2018-2019
    assert p.loc["2012-06":"2012-09"].notna().all()
    raw = load_record(correct_seasons_to_station=False)
    assert 0.9 < (t - raw.data["t_c"].reindex(t.index)).mean() < 1.3  # ERA5-Land is ~1.1 °C too cold at the station


@pytest.mark.skipif(not __import__("himsim.climate.kyanjin", fromlist=["aws_available"]).aws_available(),
                    reason="Kyanjing AWS download not present")
def test_seasonal_correction_constants_match_station_file():
    from himsim.climate.kyanjin import (AWS_MINUS_ERA5LAND, AWS_OFFSET_YEARS, load_kyanjing_aws,
                                        station_temperature_offsets)

    o = station_temperature_offsets(load_kyanjing_aws(), load_record(correct_seasons_to_station=False))
    np.testing.assert_allclose(o["offset_c"], AWS_MINUS_ERA5LAND, atol=0.006)
    assert tuple(o["years"]) == AWS_OFFSET_YEARS


@pytest.mark.skipif(not _HAVE_YALA_AWS, reason="ICIMOD Langtang AWS downloads not present")
def test_radiation_constants_match_station_files():
    from himsim.climate.icimod_aws import radiation_inputs

    measured, defaults = radiation_inputs(), ClimateParams()
    for key, value in measured.items():
        assert getattr(defaults, key) == pytest.approx(value), key
    assert defaults.albedo_ice < 0.4 <= defaults.albedo_snow
    assert min(defaults.sw_in[6:9]) < 0.6 * max(defaults.sw_in[2:5])  # monsoon clouds cut the sunshine


@pytest.mark.skipif(not _HAVE_YALA_AWS, reason="ICIMOD Langtang AWS downloads not present")
def test_lapse_rate_constants_match_station_files():
    from himsim.climate.icimod_aws import KYANJING, YALA_BASE_CAMP, lapse_rates, load_aws
    from himsim.climate.kyanjin import KYANJIN_TO_BASE_CAMP_LAPSE, LAPSE_YEARS

    lr = lapse_rates(load_aws(KYANJING), load_aws(YALA_BASE_CAMP))
    g = lr.groupby(lr.index.month)["lapse_c_per_km"]
    np.testing.assert_allclose(g.mean(), KYANJIN_TO_BASE_CAMP_LAPSE, atol=0.006)
    assert tuple(g.size()) == LAPSE_YEARS
    assert load_record().monthly_lapse[6] == pytest.approx(KYANJIN_TO_BASE_CAMP_LAPSE[6] / 1000)


def test_station_faults_moves_and_lapse_rates():
    from himsim.climate.icimod_aws import AwsStation, lapse_rates, remove_bad_periods

    station = AwsStation("test", "x", "x.csv", "X", 5000.0, 0.0, 0.0, "rock", "src",
                         moves=(("2018-11-28", 5040.0),),
                         bad_periods=(("2016-06-13", "2016-06-14", "sensor fault"),
                                      ("2016-06-20", "2016-06-21", "precipitation flagged")))
    idx = pd.date_range("2016-06-12 00:30", periods=24 * 10, freq="h")
    hourly = pd.DataFrame({"TAIR": 1.0, "PVOL": 0.5, "BCON": 100.0}, index=idx)
    clean = remove_bad_periods(hourly, station)
    assert clean.loc["2016-06-13", ["TAIR", "PVOL"]].isna().all().all()  # a sensor fault blanks everything
    assert clean.loc["2016-06-20", "TAIR"].notna().all()  # a precipitation flag keeps the temperature ...
    assert clean.loc["2016-06-20", "PVOL"].isna().all()  # ... and blanks the gauge
    assert station.elevation_on("2018-11-01") == 5000.0 and station.elevation_on("2019-01-01") == 5040.0

    months = pd.date_range("2018-01-01", periods=3, freq="MS")
    low = ClimateRecord("low", 4000.0, pd.DataFrame({"t_c": [5.0, 6.0, 7.0], "z_m": 4000.0}, index=months))
    high = ClimateRecord("high", 5000.0, pd.DataFrame({"t_c": [-1.0, np.nan, 1.5], "z_m": 5000.0}, index=months))
    lr = lapse_rates(low, high)
    assert list(lr["lapse_c_per_km"]) == pytest.approx([6.0, 5.5])  # the month without data is skipped


@pytest.mark.skipif(not _HAVE_YALA_AWS, reason="ICIMOD Langtang AWS downloads not present")
def test_langtang_stations_known_facts():
    """The real files: known faults removed, and the measured cooling with height."""
    from himsim.climate.icimod_aws import KYANJING, YALA_BASE_CAMP, YALA_GLACIER, lapse_rates, load_aws

    ky, bc, gl = load_aws(KYANJING), load_aws(YALA_BASE_CAMP), load_aws(YALA_GLACIER)
    assert np.isnan(bc.data.loc["2019-12-01", "t_c"])  # columns misaligned from 18 Nov 2019
    assert bc.data.loc["2016-06-01", "t_c"] < 3.0  # sensor-fault hours (up to 32 °C) removed
    assert bc.data.loc["2015-06-01":"2015-09-01", "t_c"].isna().all()  # destroyed by the April 2015 earthquake
    assert gl.data["z_m"].min() == 5291.0 and gl.data.loc["2019-07-01", "z_m"] == 5330.0
    lr = lapse_rates(ky, bc)
    monsoon = lr[lr.index.month.isin([6, 7, 8, 9])]["lapse_c_per_km"].mean()
    assert 5.3 < lr["lapse_c_per_km"].mean() < 6.0  # measured: 5.7 °C/km
    assert monsoon < 5.5  # measured: ~5.1 °C/km, gentler than the model's 6
    on_ice = lapse_rates(bc, gl)
    assert 1.5 < (on_ice["t_low"] - on_ice["t_high"]).mean() < 2.3  # the ice chills the air above it (~1.9 °C)
