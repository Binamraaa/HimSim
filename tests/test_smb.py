import numpy as np
import pytest

from himsim.glacier.climate import ClimateParams, Scenario
from himsim.glacier.smb import annual_smb, calibrate_temperature, equilibrium_line_altitude, glacier_wide_smb


def test_smb_increases_with_elevation():
    z = np.arange(4000.0, 7000.0, 100.0)
    smb = annual_smb(z, ClimateParams())
    assert (np.diff(smb) > 0).all()


def test_smb_is_zero_at_ela():
    c = ClimateParams()
    ela = equilibrium_line_altitude(c)
    assert 4500 < ela < 6500
    assert annual_smb(np.array(ela), c) == pytest.approx(0.0, abs=1e-3)


def test_warming_raises_ela_by_about_one_over_lapse_rate():
    c = ClimateParams()
    rise = equilibrium_line_altitude(c, temp_delta=1.0) - equilibrium_line_altitude(c)
    assert 0.5 / c.lapse_rate < rise < 1.5 / c.lapse_rate


def test_more_precipitation_lowers_ela():
    c = ClimateParams()
    assert equilibrium_line_altitude(c, precip_factor=1.3) < equilibrium_line_altitude(c)


def test_monthly_precip_shares_sum_to_one():
    assert ClimateParams().monthly_precip_share().sum() == pytest.approx(1.0)


def test_calibration_hits_target():
    z = np.linspace(5100, 5700, 50)
    mask = np.ones_like(z, dtype=bool)
    c = calibrate_temperature(z, mask, ClimateParams(), target_smb=-0.5)
    assert glacier_wide_smb(z, mask, c) == pytest.approx(-0.5, abs=1e-3)


def test_scenario_trends():
    s = Scenario(temp_offset=1.0, temp_trend=0.5, precip_change=0.1, precip_trend=0.1)
    assert s.temp_delta(0) == 1.0
    assert s.temp_delta(20) == pytest.approx(2.0)
    assert s.precip_factor(10) == pytest.approx(1.1 * 1.1)
