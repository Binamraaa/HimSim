import numpy as np
import pytest

from himsim import store
from himsim.glacier.climate import ClimateChange, ClimateParams
from himsim.glacier.observations import YALA_MEASUREMENTS, Measurement
from himsim.glacier.sites import DATA_ROOT, SITES
from himsim.glacier.smb import SmbTable, annual_smb

YALA_DEMS = (DATA_ROOT / SITES["Yala"].dems[1981]).exists()


def test_smb_table_matches_direct_calculation():
    z = np.linspace(4900.0, 5900.0, 777)
    c = ClimateParams()
    np.testing.assert_allclose(SmbTable(4800.0, 6000.0)(z, c, 0.7, 1.1), annual_smb(z, c, 0.7, 1.1), atol=2e-3)


def test_gradual_change_reaches_target_then_holds():
    s = ClimateChange(warming=2.0, precip=-0.2, target_year=2100).scenario(2025, 2150)
    assert s.temp_delta(0) == pytest.approx(0.0)
    assert s.temp_delta(75) == pytest.approx(2.0)
    assert s.temp_delta(125) == pytest.approx(2.0)  # holds after 2100
    assert s.precip_factor(75) == pytest.approx(0.8)


def test_sudden_change_applies_immediately():
    s = ClimateChange(warming=-1.0, precip=0.2, gradual=False).scenario(2025, 2100)
    assert s.temp_delta(0) == s.temp_delta(60) == pytest.approx(-1.0)
    assert s.precip_factor(0) == pytest.approx(1.2)


def test_measurement_grading():
    with_error = Measurement("q", "x", -0.80, "m", "src", uncertainty=0.28)
    assert with_error.grade(-0.60) == "matches"
    assert with_error.grade(-0.45) == "off"  # outside ±0.28 and >25 % away
    no_error = Measurement("q", "x", 60.0, "m", "src")
    assert no_error.grade(65.0) == "matches"  # within 10 %
    assert no_error.grade(72.0) == "close"  # within 25 %
    assert no_error.grade(80.0) == "off"
    ranged = Measurement("q", "x", 5449.0, "m", "src", low=5380.0, high=5518.0)
    assert ranged.grade(5500.0) == "matches"


def test_every_measurement_is_sourced():
    for m in YALA_MEASUREMENTS:
        assert "doi:" in m.source, m.what


def test_disk_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CACHE_DIR", tmp_path)
    calls = []

    def compute():
        calls.append(1)
        return {"a": np.arange(3)}

    first = store.cached("unit", ("k", 1), compute)
    second = store.cached("unit", ("k", 1), compute)
    np.testing.assert_array_equal(first["a"], second["a"])
    assert len(calls) == 1
    store.cached("unit", ("k", 2), compute)
    assert len(calls) == 2


@pytest.mark.skipif(not YALA_DEMS, reason="Yala DEMs not present")
def test_yala_reality_check():
    """Regression guard: the model keeps matching the independent field measurements."""
    from himsim.climate.kyanjin import load_record
    from himsim.glacier.history import prepare_history
    from himsim.glacier.sites import prepare_site
    from himsim.glacier.validation import reality_check, yearly_mass_balance

    data = prepare_site("Yala", 50.0)
    hist = prepare_history(data, load_record())
    rc = reality_check(data, hist).set_index("question")
    assert rc.loc["How much ice was in the glacier in 2009?", "grade"] == "matches"
    assert rc.loc["… and in 2009, measured with radar?", "grade"] == "matches"
    assert rc.loc["Average yearly mass balance 2011–2017", "grade"] == "matches"
    assert rc.loc["How fast did the surface drop, 2007–2015?", "grade"] == "matches"  # since the measured lapse rates
    assert (rc["grade"] == "matches").sum() >= 7
    assert (rc["grade"] == "off").sum() <= 1  # known: SMB gradient 0.70 vs 1.04
    assert len(yearly_mass_balance(hist, dict(data.site.yearly_mass_balance))) == 6


@pytest.mark.skipif(not YALA_DEMS, reason="Yala DEMs not present")
def test_yala_climate_matches_kyanjing_station():
    """With the station's seasons and measured lapse rates, the tuned model matches Kyanjing with almost no tuning."""
    from himsim.climate.kyanjin import aws_available, load_kyanjing_aws, load_record
    from himsim.glacier.history import prepare_history
    from himsim.glacier.sites import prepare_site
    from himsim.glacier.validation import station_comparison

    if not aws_available():
        pytest.skip("Kyanjing AWS download not present")
    record = load_record()
    hist = prepare_history(prepare_site("Yala", 50.0), record)
    sc = station_comparison(hist, record, load_kyanjing_aws())
    t = sc.dropna(subset=["station_t_c"])
    warmer = t["model_t_c"] - t["station_t_c"]
    summer, winter = warmer[t.index.month.isin([6, 7, 8, 9])].mean(), warmer[t.index.month.isin([12, 1, 2])].mean()
    assert abs(summer - winter) < 0.6  # seasons fixed (were +1.4 / -1.4 °C before the correction)
    assert abs(warmer.mean()) < 0.3  # was +1.34 °C with a constant 6 °C/km
    raw = ClimateParams.from_record(record, *hist.calibration_period).t_annual_ref
    assert abs(hist.climate.t_annual_ref - raw) < 0.4  # the calibration shift itself: +0.24 °C


@pytest.mark.skipif(not YALA_DEMS, reason="Yala DEMs not present")
def test_yala_model_monsoon_matches_base_camp():
    """In the melt season the tuned model's air at Yala Base Camp (5090 m) is close to the thermometer."""
    from himsim.climate.icimod_aws import YALA_BASE_CAMP, load_aws
    from himsim.climate.kyanjin import load_record
    from himsim.glacier.history import prepare_history
    from himsim.glacier.sites import prepare_site
    from himsim.glacier.validation import station_comparison

    if not YALA_BASE_CAMP.available():
        pytest.skip("Yala Base Camp AWS download not present")
    record = load_record()
    hist = prepare_history(prepare_site("Yala", 50.0), record)
    sc = station_comparison(hist, record, load_aws(YALA_BASE_CAMP)).dropna(subset=["station_t_c"])
    monsoon = sc[sc.index.month.isin([6, 7, 8, 9])]
    assert abs((monsoon["model_t_c"] - monsoon["station_t_c"]).mean()) < 0.5  # +0.30 °C (+0.37 with 6 °C/km)
