import numpy as np
import pandas as pd
import pytest

from himalsim.climate.kyanjin import KYANJIN, load_record
from himalsim.climate.record import ClimateRecord
from himalsim.glacier.climate import ClimateParams
from himalsim.glacier.history import historical_scenario


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
