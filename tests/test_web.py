"""The student website's API: every page's data loads, numbers match the model, and inputs are validated."""

import json
import re
from pathlib import Path

import pytest

from himsim.glacier.sites import DATA_ROOT, SITES

pytestmark = pytest.mark.skipif(not (DATA_ROOT / SITES["Yala"].dems[1981]).exists(), reason="Yala DEMs not present")
STATIC = Path(__file__).resolve().parents[1] / "web" / "static"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from web.api import app

    with TestClient(app) as c:
        yield c


def test_static_site_is_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "HimSim" in page.text
    for asset in ("styles.css", "app.js", "guide.js"):
        assert (STATIC / asset).exists() and asset in page.text
    js = client.get("/vendor/plotly.min.js")
    assert js.status_code == 200 and len(js.content) > 1_000_000  # served from the installed plotly package


def test_guide_covers_every_hooked_section():
    """Each part of the page that shows a hover tip has guide text, and every page with missions has some."""
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    guide = (STATIC / "guide.js").read_text(encoding="utf-8")
    hooked = set(re.findall(r'data-guide="([\w-]+)"', page))
    explained = set(re.findall(r'^    "([\w-]+)": \{$', guide, flags=re.M))
    assert hooked and hooked == explained
    assert set(re.findall(r'data-guide-open="([\w-]+)"', page)) <= hooked
    mission_pages = set(re.findall(r'data-missions="(\w+)"', page))
    assert mission_pages == set(re.findall(r'page: "(\w+)"', guide)) == {"meet", "future", "trust"}


def test_overview_matches_the_history_run(client):
    o = client.get("/api/overview").json()
    assert o["site"]["start_year"] == 1981 and o["site"]["surveys"] == [1981, 2007, 2015]
    assert 0 < o["lost_pct"] < 100
    assert o["radar"][0]["year"] == 2009
    assert o["volume_figure"]["data"]


def test_future_runs_compare_and_validate(client):
    d = client.post("/api/future", json={"scenario": {"warming": 2.0}, "kept": [{"warming": 4.0}]}).json()
    assert d["label"] == "+2.0 °C by 2100" and not d["is_baseline"]
    assert "is gone by about" in d["headline"]
    assert [r["scenario"] for r in d["table"]] == ["Today's climate continues", "+4.0 °C by 2100", "+2.0 °C by 2100"]
    assert d["colors"]["+4.0 °C by 2100"] != d["colors"]["+2.0 °C by 2100"]  # each scenario keeps its own colour
    assert len(d["series"]) == 3 and d["series"][0]["year"][0] == d["snapshot_years"][0]

    base = client.post("/api/future", json={"scenario": {"warming": 0.0}}).json()
    assert base["is_baseline"] and base["headline"].startswith("If today's climate continues")

    assert client.post("/api/future", json={"scenario": {"warming": 9.0}}).status_code == 422  # outside the slider
    too_many = [{"warming": 0.1 * i} for i in range(8)]
    assert client.post("/api/future", json={"kept": too_many}).status_code == 422


def test_future_views(client):
    fig = client.get("/api/future-3d", params={"warming": 2.0}).json()
    assert fig["frames"] and fig["layout"]["sliders"]
    maps = client.get("/api/future-maps", params={"warming": 2.0, "year": 2061}).json()
    assert maps["year"] in range(2025, 2101) and maps["thickness_figure"]["data"] and maps["change_figure"]["data"]


def test_deploy_bundle_round_trip(tmp_path, monkeypatch):
    """The website gives the same answers from the deploy bundle (no DEMs, no station files) as from the raw data."""
    import numpy as np

    from web import api, bundle

    built = api.build_model(with_station_summary=True)
    path = bundle.save(built, tmp_path / "bundle.pkl.gz")
    assert path.stat().st_size < 5_000_000  # small enough for any free host
    loaded = bundle.load(path)
    assert np.array_equal(loaded.hist.present_thickness, built.hist.present_thickness)
    assert loaded.period == built.period and loaded.today == built.today

    if built.stations:  # statistics only: numbers and labels, nothing per hour or per month
        flat = json.dumps(built.stations)
        assert len(flat) < 2000 and set(built.stations) == {"bias", "base_camp", "on_ice_colder"}

    original = api.reality()
    monkeypatch.setattr(api, "_model", loaded)
    monkeypatch.setattr(api, "_stations", lambda: {})  # as on a host without the ICIMOD files
    from_bundle = api.reality()
    if built.stations:
        assert from_bundle == original
    else:
        assert from_bundle["counts"] == original["counts"]


def test_reality_and_learn_pages(client):
    r = client.get("/api/reality").json()
    assert sum(r["counts"].values()) == len(r["rows"])
    assert r["counts"]["matches"] >= 7  # same guard as test_yala_reality_check
    assert r["bands_figure"]["data"] and r["method"]["sources"]
    learn = client.get("/api/learn").json()
    assert "<h" in learn["explainer_html"] and learn["climate"]["annual_figure"]["data"]
