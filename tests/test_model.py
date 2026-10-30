import numpy as np
import pytest

from himalsim.glacier.climate import ClimateParams, Scenario
from himalsim.glacier.model import simulate
from himalsim.glacier.sites import DATA_ROOT, SITES
from himalsim.glacier.thickness import initial_thickness, volume_area_scaling


def _valley(n=40, dx=50.0):
    """A synthetic valley sloping from 5500 m down to 5100 m, so the default ELA (~5220 m) crosses the glacier."""
    y, x = np.mgrid[0:n, 0:n] * dx
    bed = 5500.0 - 0.2 * y + 0.002 * (x - x.mean()) ** 2
    mask = np.zeros((n, n), dtype=bool)
    mask[3:30, 12:28] = True
    return bed, mask, dx


def test_no_mass_balance_conserves_volume():
    bed, mask, dx = _valley()
    h0 = np.where(mask, 40.0, 0.0)
    frozen_dry = ClimateParams(t_annual_ref=-60.0, p_annual_ref=0.0)  # no melt, no snow
    r = simulate(bed, h0, dx, frozen_dry, Scenario(years=20), accumulation_mask=mask)
    assert r.volume[-1] == pytest.approx(r.volume[0], rel=1e-6)
    assert r.outflow_m3 == 0.0


def test_warming_shrinks_and_cooling_grows():
    bed, mask, dx = _valley()
    h0 = initial_thickness(bed, mask, dx)
    c = ClimateParams()
    runs = {dt: simulate(bed, h0, dx, c, Scenario(years=30, temp_offset=dt), accumulation_mask=mask)
            for dt in (-3.0, 0.0, 3.0)}
    assert runs[3.0].volume[-1] < runs[0.0].volume[-1] < runs[-3.0].volume[-1]
    assert np.isfinite(runs[3.0].final_thickness).all() and (runs[3.0].final_thickness >= 0).all()


def test_no_new_ice_forms_outside_accumulation_mask():
    """Ice may flow out of the mask, but cells far from it must stay ice-free even with positive SMB."""
    from scipy.ndimage import distance_transform_edt

    bed, mask, dx = _valley()
    cold = ClimateParams(t_annual_ref=-20.0)  # positive SMB everywhere
    r = simulate(bed, np.zeros_like(bed), dx, cold, Scenario(years=5), accumulation_mask=mask)
    far = distance_transform_edt(~mask) > 4
    assert (r.final_thickness[far] == 0).all()
    assert (r.final_thickness[mask] > 0).all()


def test_thickness_ignores_terrain_outside_glacier():
    """A ridge crest beyond the outline must not change the glacier's own thickness."""
    bed, mask, dx = _valley()
    ridge = bed.copy()
    ridge[~mask] += 500.0
    assert np.allclose(initial_thickness(bed, mask, dx), initial_thickness(ridge, mask, dx))


def test_ice_domain_blocks_spill_over_ridge():
    """Ice may advance down-valley but not across faces leaving the ice domain."""
    from himalsim.glacier.sites import ice_domain_mask

    n, dx = 30, 50.0
    y = np.mgrid[0:n, 0:n][0] * dx
    bed = 5600.0 - 0.3 * y  # slopes down toward increasing row
    bed[3, :] = 5700.0  # ridge crest just above the glacier
    bed[:3, :] = 5300.0  # the far side of the ridge, lower than the glacier top
    mask = np.zeros((n, n), dtype=bool)
    mask[4:15, 10:20] = True
    domain = ice_domain_mask(bed, mask)
    assert not domain[:4].any() and domain[25:, 10:20].all()
    h0 = np.where(mask, 60.0, 0.0)
    h0[4, 10:20] = 120.0  # thick ice at the top, surface above the crest: would spill without the domain
    frozen = ClimateParams(t_annual_ref=-60.0, p_annual_ref=0.0)
    r = simulate(bed, h0, dx, frozen, Scenario(years=10), accumulation_mask=mask, ice_domain=domain)
    assert (r.final_thickness[:4] == 0).all()
    assert r.volume[-1] == pytest.approx(r.volume[0], rel=1e-9)


def test_scaled_thickness_matches_volume_area_scaling():
    bed, mask, dx = _valley()
    h = initial_thickness(bed, mask, dx)
    assert h.sum() * dx * dx == pytest.approx(volume_area_scaling(mask.sum() * dx * dx))
    assert (h[~mask] == 0).all()


@pytest.mark.skipif(not (DATA_ROOT / SITES["Yala"].dems[1981]).exists(), reason="Yala DEMs not present")
def test_yala_history_matches_observed_thinning():
    """Regression guard on the real data, replaying the Kyanjin weather 1981 -> today.

    The calibration only fixes the 1981-2015 average, so the faster thinning after 2007
    must come from the observed weather itself.
    """
    from himalsim.climate.kyanjin import load_record
    from himalsim.glacier.history import run_history
    from himalsim.glacier.sites import load_site

    data = load_site(SITES["Yala"], dx=50.0, use_copernicus=False)
    h = run_history(data, load_record())
    rates = h.rates.set_index("period")
    assert abs(rates.loc["1981-2015", "modeled_m_per_yr"] - rates.loc["1981-2015", "observed_m_per_yr"]) < 0.1
    assert rates.loc["2007-2015", "modeled_m_per_yr"] < rates.loc["1981-2007", "modeled_m_per_yr"]  # speed-up
    assert 0.5 < h.result.area[-1] / h.result.area[0] < 1.0  # shrinking, but still there today
