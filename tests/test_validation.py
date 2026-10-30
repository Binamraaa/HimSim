import numpy as np
import pytest

from himalsim import store
from himalsim.glacier.climate import ClimateChange, ClimateParams
from himalsim.glacier.observations import YALA_MEASUREMENTS, Measurement
from himalsim.glacier.sites import DATA_ROOT, SITES
from himalsim.glacier.smb import SmbTable, annual_smb

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
    from himalsim.climate.kyanjin import load_record
    from himalsim.glacier.history import prepare_history
    from himalsim.glacier.sites import prepare_site
    from himalsim.glacier.validation import reality_check, yearly_mass_balance

    data = prepare_site("Yala", 50.0)
    hist = prepare_history(data, load_record())
    rc = reality_check(data, hist).set_index("question")
    assert rc.loc["How much ice was in the glacier in 2009?", "grade"] == "matches"
    assert rc.loc["… and in 2009, measured with radar?", "grade"] == "matches"
    assert rc.loc["Average yearly mass balance 2011–2017", "grade"] == "matches"
    assert (rc["grade"] == "matches").sum() >= 6
    assert len(yearly_mass_balance(hist, dict(data.site.yearly_mass_balance))) == 6
