"""Site registry: open DEM sources and the Rikha Samba domain."""

import json

import numpy as np
import pytest

from himsim.dem import srtm_tile_url
from himsim.glacier.sites import SITES, load_site


def test_srtm_tile_names():
    assert srtm_tile_url(28, 83).endswith("/skadi/N28/N28E083.hgt.gz")
    assert srtm_tile_url(-1, -71).endswith("/skadi/S01/S01W071.hgt.gz")


def test_rikha_samba_domain_matches_rgi():
    """SRTM 2000 surface inside the RGI 6.0 outline reproduces the RGI area and elevations (needs internet once)."""
    site = SITES["Rikha Samba"]
    with open(site.outline_geojson) as f:
        rgi = json.load(f)["features"][0]["properties"]
    try:
        data = load_site(site, dx=50.0)
    except OSError as exc:  # first run offline: SRTM/Copernicus tiles not cached yet
        pytest.skip(f"open DEMs unavailable: {exc}")
    m = data.mask
    assert abs(m.sum() * 50.0**2 / 1e6 - rgi["area_km2"]) < 0.05 * rgi["area_km2"]
    assert abs(np.median(data.surface[m]) - rgi["zmed"]) < 30
    assert abs(data.surface[m].min() - rgi["zmin"]) < 50 and abs(data.surface[m].max() - rgi["zmax"]) < 50
    # Copernicus terrain and SRTM agree on rock to within a few metres (datums both converted to EGM2008)
    assert abs(np.median((data.observed[2000] - data.observed[2013])[~m])) < 6
    assert data.ice_domain[m].all() and np.isfinite(data.bed).all()
