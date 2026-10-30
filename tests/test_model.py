import numpy as np
import pytest

from himalsim.glacier.climate import ClimateParams, Scenario
from himalsim.glacier.model import simulate
from himalsim.glacier.sites import DATA_ROOT, SITES
from himalsim.glacier.thickness import initial_thickness, volume_area_scaling


def _valley(n=40, dx=50.0):
    """A synthetic valley sloping from 5800 m down to 5000 m."""
    y, x = np.mgrid[0:n, 0:n] * dx
    bed = 5800.0 - 0.2 * y + 0.002 * (x - x.mean()) ** 2
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
    warm = simulate(bed, h0, dx, c, Scenario(years=30, temp_offset=3.0), accumulation_mask=mask)
    cold = simulate(bed, h0, dx, c, Scenario(years=30, temp_offset=-3.0), accumulation_mask=mask)
    assert warm.volume[-1] < warm.volume[0]
    assert cold.volume[-1] > cold.volume[0]
    assert np.isfinite(warm.final_thickness).all() and (warm.final_thickness >= 0).all()


def test_no_new_ice_forms_outside_accumulation_mask():
    """Ice may flow out of the mask, but cells far from it must stay ice-free even with positive SMB."""
    from scipy.ndimage import distance_transform_edt

    bed, mask, dx = _valley()
    cold = ClimateParams(t_annual_ref=-20.0)  # positive SMB everywhere
    r = simulate(bed, np.zeros_like(bed), dx, cold, Scenario(years=5), accumulation_mask=mask)
    far = distance_transform_edt(~mask) > 4
    assert (r.final_thickness[far] == 0).all()
    assert (r.final_thickness[mask] > 0).all()


def test_scaled_thickness_matches_volume_area_scaling():
    bed, mask, dx = _valley()
    h = initial_thickness(bed, mask, dx)
    assert h.sum() * dx * dx == pytest.approx(volume_area_scaling(mask.sum() * dx * dx))
    assert (h[~mask] == 0).all()


@pytest.mark.skipif(not (DATA_ROOT / SITES["Yala"].dems[1981]).exists(), reason="Yala DEMs not present")
def test_yala_hindcast_matches_observed_thinning():
    """Regression guard on the real data: 1981->2015 glacier-mean thinning within 5 m of the DEMs."""
    from himalsim.glacier.sites import load_site
    from himalsim.glacier.validation import calibrated_climate, hindcast

    data = load_site(SITES["Yala"], dx=50.0)
    climate, _ = calibrated_climate(data)
    _, comps = hindcast(data, climate)
    df = comps[2015]
    obs = np.average(df["observed_dh"], weights=df["cells"])
    mod = np.average(df["modeled_dh"], weights=df["cells"])
    assert abs(obs - mod) < 5.0
