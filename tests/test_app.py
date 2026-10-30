"""Headless smoke test of the Streamlit app: every step renders and the controls drive the model."""

from pathlib import Path

import pytest

from himsim.glacier.sites import DATA_ROOT, SITES

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
pytestmark = pytest.mark.skipif(not (DATA_ROOT / SITES["Yala"].dems[1981]).exists(), reason="Yala DEMs not present")


def _headline(at):
    return next(md.value for md in at.markdown if md.value.startswith("### "))


def test_app_runs_and_responds():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(APP), default_timeout=600).run()
    assert not at.exception
    assert "+2.0 °C by 2100" in _headline(at)

    at.radio(key="preset").set_value("Cooler").run()
    assert at.session_state["warming"] == pytest.approx(-1.0)
    assert "from today" in _headline(at)

    at.slider(key="warming").set_value(4.0).run()
    assert at.session_state["preset"] is None  # moving a slider deselects the idea
    assert "is gone by about" in _headline(at)

    next(b for b in at.button if "Keep" in b.label).click().run()
    assert list(at.session_state["kept"]) == ["+4.0 °C from today"]
    assert not at.exception
