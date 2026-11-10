"""HimSim student website server: the JSON API behind ``web/static``.

Run with ``python -m web`` and open http://127.0.0.1:8600. This file is only the HTTP layer (routes, input
validation, static files); every answer comes from ``web/core.py``, which the static in-browser site runs too.

On a host without the survey DEMs and station files, set ``HIMSIM_WEB_BUNDLE`` to a bundle built with
``python -m web.bundle``; see ``web/bundle.py``.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import plotly
from fastapi import FastAPI, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web import core
from web.core import MAX_KEPT, Model, build_model, model  # noqa: F401  (Model: old bundles pickled web.api.Model)

STATIC = Path(__file__).with_name("static")
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


class ScenarioIn(BaseModel):
    warming: float = Field(2.0, ge=-2.0, le=5.0, description="°C, relative to today's climate")
    precip_pct: int = Field(0, ge=-50, le=50, description="% change in rain and snow")
    gradual: bool = True
    end_year: int = Field(2100, ge=2050, le=2200)

    def to_core(self) -> core.ScenarioIn:
        return core.ScenarioIn(self.warming, self.precip_pct, self.gradual, self.end_year)


class FutureIn(BaseModel):
    scenario: ScenarioIn = ScenarioIn()
    kept: list[ScenarioIn] = Field(default_factory=list, max_length=MAX_KEPT)


def _scenario_query(warming: float = Query(2.0, ge=-2.0, le=5.0), precip_pct: int = Query(0, ge=-50, le=50),
                    gradual: bool = True, end_year: int = Query(2100, ge=2050, le=2200)) -> core.ScenarioIn:
    return core.ScenarioIn(warming, precip_pct, gradual, end_year)


@asynccontextmanager
async def _lifespan(_app):
    if not logging.getLogger().handlers:  # worker processes don't inherit the launcher's logging setup
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    threading.Thread(target=core.warm_up, daemon=True).start()  # build the glacier while the page loads
    yield


app = FastAPI(title="HimSim", description=__doc__, lifespan=_lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2000)


@app.get("/api/overview")
def overview() -> dict:
    return core.overview()


@app.get("/api/past-3d")
def past_3d() -> dict:
    return core.past_3d()


@app.get("/api/presets")
def presets() -> dict:
    return core.presets()


@app.post("/api/future")
def future_results(body: FutureIn) -> dict:
    return core.future_results(core.FutureIn(body.scenario.to_core(), tuple(k.to_core() for k in body.kept)))


@app.get("/api/future-3d")
def future_3d(warming: float = Query(2.0, ge=-2.0, le=5.0), precip_pct: int = Query(0, ge=-50, le=50),
              gradual: bool = True, end_year: int = Query(2100, ge=2050, le=2200)) -> dict:
    return core.future_3d(_scenario_query(warming, precip_pct, gradual, end_year))


@app.get("/api/future-maps")
def future_maps(year: int, warming: float = Query(2.0, ge=-2.0, le=5.0), precip_pct: int = Query(0, ge=-50, le=50),
                gradual: bool = True, end_year: int = Query(2100, ge=2050, le=2200)) -> dict:
    return core.future_maps(year, _scenario_query(warming, precip_pct, gradual, end_year))


@app.get("/api/reality")
def reality() -> dict:
    return core.reality()


@app.get("/api/learn")
def learn() -> dict:
    return core.learn()


@app.get("/vendor/plotly.min.js")
def plotly_js() -> FileResponse:
    """Plotly.js from the installed Python package, so the site works without internet."""
    return FileResponse(PLOTLY_JS, media_type="application/javascript", headers={"Cache-Control": "max-age=86400"})


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
