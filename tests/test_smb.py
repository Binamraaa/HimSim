import numpy as np
import pytest

from himsim.constants import WE_TO_ICE
from himsim.glacier.climate import DAYS_IN_MONTH, ClimateParams, Scenario
from himsim.glacier.smb import annual_smb, calibrate_temperature, equilibrium_line_altitude, glacier_wide_smb, melt_rates


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


def test_equal_melt_factors_give_the_single_factor_model():
    z = np.linspace(4500.0, 6500.0, 41)
    c = ClimateParams(ddf=0.008, ddf_snow=0.008)
    temp, precip = c.monthly_temperature(z), c.monthly_precipitation(z)
    days = DAYS_IN_MONTH[:, None]
    snow = precip * np.clip((c.t_rain - temp) / (c.t_rain - c.t_snow), 0.0, 1.0)
    single = (snow - c.ddf * np.maximum(temp - c.t_melt, 0.0) * days).sum(axis=0) * WE_TO_ICE
    np.testing.assert_allclose(annual_smb(z, c), single, atol=1e-9)


def test_snow_melts_slower_than_ice():
    c = ClimateParams()
    assert c.ddf_snow < c.ddf
    no_snow = c.with_changes(t_snow=-50.0, t_rain=-40.0)  # all precipitation is rain: bare ice all year
    z = np.array(4000.0)
    temp = no_snow.monthly_temperature(z)
    days = DAYS_IN_MONTH
    ice_melt = c.ddf * (np.maximum(temp - c.t_melt, 0.0) * days).sum()
    assert annual_smb(z, no_snow) == pytest.approx(-ice_melt * WE_TO_ICE, rel=1e-9)
    # a snowpack that never melts away shields the ice: high and cold, melt only at the snow rate
    high = np.array(7000.0)
    assert annual_smb(high, c) > 0


def test_separate_factors_steepen_the_smb_gradient():
    """Snow covers the upper glacier longer, so with slower snow melt the SMB rises faster with height."""
    single, split = ClimateParams(ddf=0.00863, ddf_snow=0.00863), ClimateParams()
    def gradient(c):
        ela = equilibrium_line_altitude(c)
        b = annual_smb(np.array([ela - 50.0, ela + 50.0]), c)
        return b[1] - b[0]
    assert gradient(split) > gradient(single)


def test_sunshine_melt_switches_on_smoothly():
    c = ClimateParams(melt_model="eti")
    temp = np.repeat(np.linspace(-10.0, 5.0, 301)[None, :], 12, axis=0)
    snow, ice = melt_rates(temp, c)
    july_snow, july_ice = snow[6], ice[6]
    assert july_ice[0] == pytest.approx(0.0, abs=1e-9)  # far below freezing: no warm days, no melt
    assert (np.diff(july_ice) >= 0).all() and np.abs(np.diff(july_ice)).max() < 1e-3  # no jump at 0 °C
    assert (july_ice >= july_snow).all()  # dark ice absorbs more sunshine than bright snow
    warm = july_ice[-1] - july_snow[-1]  # all days warm: the difference is the albedo term alone
    assert warm == pytest.approx(c.srf * c.sw_in[6] * (c.albedo_snow - c.albedo_ice), rel=1e-3)


def test_sunshine_model_runs_and_differs():
    z = np.linspace(4500.0, 6500.0, 21)
    ti, eti = annual_smb(z, ClimateParams()), annual_smb(z, ClimateParams(melt_model="eti"))
    assert np.isfinite(eti).all() and (np.diff(eti) > 0).all()
    assert not np.allclose(ti, eti)
    with pytest.raises(ValueError):
        annual_smb(z, ClimateParams(melt_model="sunny"))


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
