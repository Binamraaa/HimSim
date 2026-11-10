"""The website's in-browser front door: ``web/static/pyworker.js`` runs this inside Pyodide (Python compiled to
WebAssembly) so the static site needs no server. It answers the same ``/api/...`` paths as ``web/api.py`` with the
same JSON, from the same ``web.core`` functions; ``tests/test_web.py`` checks that both doors agree.
"""

from __future__ import annotations

import json
import math
from urllib.parse import parse_qsl, urlsplit

from web import core

_TRUE, _FALSE = {"true", "1", "yes", "on"}, {"false", "0", "no", "off"}


def _bool(v: str) -> bool:
    v = v.lower()
    if v in _TRUE or v in _FALSE:
        return v in _TRUE
    raise ValueError(f"expected true or false, got {v!r}")


def _number(v: str, kind) -> float | int:
    x = float(v)
    if not math.isfinite(x):
        raise ValueError(f"not a finite number: {v!r}")
    if kind is int:
        if x != int(x):
            raise ValueError(f"expected a whole number, got {v!r}")
        return int(x)
    return x


def _scenario(q: dict) -> core.ScenarioIn:
    return core.ScenarioIn(warming=_number(q.get("warming", "2.0"), float),
                           precip_pct=_number(q.get("precip_pct", "0"), int),
                           gradual=_bool(q.get("gradual", "true")),
                           end_year=_number(q.get("end_year", "2100"), int))


def route(path: str, body: dict | None = None) -> dict:
    """The page data for ``path`` (``/api/...`` with an optional query string). ValueError for bad input."""
    url = urlsplit(path)
    q = dict(parse_qsl(url.query))
    name = url.path.rstrip("/").rsplit("/api/", 1)[-1]
    if name == "overview":
        return core.overview()
    if name == "past-3d":
        return core.past_3d()
    if name == "presets":
        return core.presets()
    if name == "future":
        return core.future_results(core.FutureIn.from_dict(body))
    if name == "future-3d":
        return core.future_3d(_scenario(q))
    if name == "future-maps":
        if "year" not in q:
            raise ValueError("year is required")
        return core.future_maps(_number(q["year"], int), _scenario(q))
    if name == "reality":
        return core.reality()
    if name == "learn":
        return core.learn()
    raise LookupError(f"no such page: {url.path}")


def handle(path: str, body_json: str | None = None) -> str:
    """``route`` for JavaScript: a JSON string ``{"status": 200, "data": ...}`` or ``{"status": 4xx, "error": ...}``."""
    try:
        data = route(path, json.loads(body_json) if body_json else None)
        return json.dumps({"status": 200, "data": data}, allow_nan=False, separators=(",", ":"))
    except LookupError as exc:
        return json.dumps({"status": 404, "error": str(exc)})
    except (ValueError, TypeError) as exc:  # bad input, like the server's 422
        return json.dumps({"status": 422, "error": str(exc)})
