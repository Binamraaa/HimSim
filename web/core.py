"""HimSim student website: everything behind the pages, without a web server.

No physics here: every number comes from ``himsim`` with the standard (literature) settings, and every chart from
``himsim.viz``, so the website and the Streamlit teacher lab show the same results. Teachers change model settings
in the lab. Two front doors use this module and must give identical answers:

* ``web/api.py``: FastAPI server (``python -m web``), adds HTTP validation;
* ``web/browser.py``: the static site, where this code runs inside the student's browser (Pyodide).

So this module must import neither FastAPI nor pydantic, nor rasterio/pyproj (unavailable in the browser).
Without the survey DEMs and station files, set ``HIMSIM_WEB_BUNDLE`` to a bundle built with
``python -m web.bundle``; see ``web/bundle.py``.
"""

from __future__ import annotations

import calendar
import json
import logging
import math
import os
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import markdown
import numpy as np
import pandas as pd

from himsim import viz
from himsim.climate.icimod_aws import KYANJING, STATIONS, YALA_BASE_CAMP, YALA_GLACIER, lapse_rates, load_aws
from himsim.climate.kyanjin import AWS_MINUS_ERA5LAND, KYANJIN, KYANJIN_TO_BASE_CAMP_LAPSE, load_record
from himsim.glacier import PRESETS, ClimateChange, ClimateParams, FlowParams, prepare_site, simulate
from himsim.glacier.climate import MONTH_NAMES
from himsim.glacier.history import HistoryRun, prepare_history
from himsim.glacier.sites import SiteData
from himsim.glacier.smb import annual_smb, equilibrium_line_altitude
from himsim.glacier.validation import reality_check, station_comparison, yearly_mass_balance

SITE, DX = "Yala", 50.0
POOL_M3 = 2500.0  # an Olympic swimming pool: 50 m × 25 m × 2 m
BASELINE = "Today's climate continues"
DEFAULT_PRESET = "+2 °C by 2100"
EXPLAINER = Path(__file__).resolve().parents[1] / "app" / "how_it_works.md"
log = logging.getLogger("himsim.web")


# ---------------------------------------------------------------- model state (built once, then cached)
@dataclass(frozen=True)
class Model:
    data: SiteData
    record: object
    period: tuple[int, int]
    hist: HistoryRun
    stations: dict | None = None  # station-check statistics (from a deploy bundle); None = read the station files

    @property
    def today(self) -> int:
        return self.hist.present_year

    @property
    def heights(self) -> np.ndarray:
        return self.data.observed[self.period[0]][self.data.mask]

    def measured_points(self) -> list[tuple[int, float, float, str]]:
        return [(dict(m.params)["year"], m.value, (m.high or m.value) - m.value, f"Measured {dict(m.params)['year']} (radar)")
                for m in self.data.site.measurements if m.kind == "volume"]


_lock = threading.Lock()
_model: Model | None = None


def build_model(with_station_summary: bool = False) -> Model:
    """Build Yala from the DEMs with standard settings (~15 s the first time, then from the disk cache)."""
    data, record = prepare_site(SITE, DX), load_record()
    period = (data.site.start_year, max(data.observed))
    base = ClimateParams.from_record(record, *period)
    hist = prepare_history(data, record, FlowParams(), base)
    stations = station_summary(hist, record, _stations()) if with_station_summary and _stations() else None
    return Model(data, record, period, hist, stations)


def model() -> Model:
    """The glacier and its 1981 → today replay: from the deploy bundle if ``HIMSIM_WEB_BUNDLE`` is set, else the DEMs."""
    global _model
    with _lock:
        if _model is None:
            bundle_path = os.environ.get("HIMSIM_WEB_BUNDLE")
            if bundle_path:
                from web import bundle

                _model = bundle.load(Path(bundle_path))
                log.info("Loaded the glacier from %s", bundle_path)
            else:
                _model = build_model()
    return _model


@lru_cache(maxsize=256)
def future(warming: float, precip_pct: int, gradual: bool, end_year: int):
    m = model()
    change = ClimateChange(warming=warming, precip=precip_pct / 100, gradual=gradual)
    run = simulate(m.data.bed, m.hist.present_thickness, DX, m.hist.present_climate,
                   change.scenario(m.today, end_year), FlowParams(),
                   accumulation_mask=m.data.mask, ice_domain=m.data.ice_domain)
    return change, run


# ---------------------------------------------------------------- helpers
def fig_json(fig) -> dict:
    return json.loads(fig.to_json())  # plotly's encoder turns NaN into null


def finite(v) -> float | None:
    v = float(v)
    return v if math.isfinite(v) else None


def million_m3(volume_m3: float) -> str:
    return f"{volume_m3 / 1e6:,.0f} million m³"


def stat(label: str, value: str, delta: str | None = None, tone: str = "neutral", help: str = "") -> dict:
    return {"label": label, "value": value, "delta": delta, "tone": tone, "help": help}


@dataclass(frozen=True)
class ScenarioIn:
    """A student's climate idea. Same limits as the website's sliders; ``ValueError`` outside them."""

    warming: float = 2.0  # °C, relative to today's climate
    precip_pct: int = 0  # % change in rain and snow
    gradual: bool = True
    end_year: int = 2100

    LIMITS = {"warming": (-2.0, 5.0), "precip_pct": (-50, 50), "end_year": (2050, 2200)}

    def __post_init__(self):
        for name, (lo, hi) in self.LIMITS.items():
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                raise ValueError(f"{name} must be a number from {lo} to {hi}, got {v!r}")
        if not isinstance(self.gradual, bool):
            raise ValueError(f"gradual must be true or false, got {self.gradual!r}")

    @classmethod
    def from_dict(cls, d: dict | None) -> ScenarioIn:
        d = dict(d or {})
        unknown = set(d) - {"warming", "precip_pct", "gradual", "end_year"}
        if unknown:
            raise ValueError(f"unknown scenario field(s): {sorted(unknown)}")
        return cls(**d)

    def key(self) -> tuple[float, int, bool, int]:
        return round(self.warming, 1), int(5 * round(self.precip_pct / 5)), self.gradual, int(10 * round(self.end_year / 10))


MAX_KEPT = len(viz.CATEGORICAL) - 1


@dataclass(frozen=True)
class FutureIn:
    scenario: ScenarioIn = field(default_factory=ScenarioIn)
    kept: tuple[ScenarioIn, ...] = ()

    def __post_init__(self):
        if len(self.kept) > MAX_KEPT:
            raise ValueError(f"at most {MAX_KEPT} kept scenarios")

    @classmethod
    def from_dict(cls, d: dict | None) -> FutureIn:
        d = dict(d or {})
        return cls(ScenarioIn.from_dict(d.get("scenario")), tuple(ScenarioIn.from_dict(k) for k in d.get("kept") or ()))


def outcome(run, today: int, end_year: int) -> str:
    if run.year_vanished is not None:
        return f"is gone by about **{today + run.year_vanished:.0f}**"
    return f"keeps **{run.volume_remaining_pct:.0f} %** of today's ice in {end_year}"


def series(name: str, run, today: int) -> dict:
    df = run.to_frame()
    return {"name": name, "year": [int(today + y) for y in run.years],
            "volume_million_m3": [round(v * 1000, 2) for v in df["volume_km3"]],
            "area_km2": [round(a, 3) for a in df["area_km2"]], "snowline_m": [round(e, 1) for e in df["ela_m"]]}


# ---------------------------------------------------------------- pages
def overview() -> dict:
    m = model()
    hist, period, today = m.hist, m.period, m.today
    v0, v_now = hist.result.volume[0], hist.result.volume[-1]
    ela_then, ela_now = equilibrium_line_altitude(hist.climate), equilibrium_line_altitude(hist.present_climate)
    zg = m.heights
    measured = m.measured_points()
    return {
        "site": {"name": "Yala Glacier", "place": "Langtang valley, Nepal", "z_min": round(float(zg.min()), -1),
                 "z_max": round(float(zg.max()), -1), "start_year": period[0], "period_end": period[1], "today": today,
                 "recent_warming": round(float(hist.recent_warming), 1),
                 "surveys": sorted(int(y) for y in m.data.observed), "village": KYANJIN.name},
        "lost_pct": round(100 * (v0 - v_now) / v0),
        "stats": [
            stat(f"Ice in {period[0]}", million_m3(v0), help=f"About {v0 / POOL_M3:,.0f} Olympic swimming pools."),
            stat(f"Ice at the end of {today}", million_m3(v_now), f"{100 * (v_now - v0) / v0:+.0f} %", "loss",
                 f"About {v_now / POOL_M3:,.0f} Olympic swimming pools."),
            stat("Change in snowline height", f"{ela_now - ela_then:+.0f} m", "higher up the mountain", "neutral",
                 f"Average {period[0]}–{period[1]}: {ela_then:,.0f} m. Average {today - 9}–{today}: {ela_now:,.0f} m. "
                 "Above the snowline a glacier gains snow each year; below it, it loses ice."),
            stat(f"{KYANJIN.name} got warmer", f"{hist.recent_warming:+.1f} °C", None, "neutral",
                 f"Average temperature {today - 9}–{today} compared with {period[0]}–{period[1]}."),
        ],
        "radar": [{"year": y, "measured_million_m3": round(v * 1000), "model_million_m3": round(hist.result.volume[y - period[0]] / 1e6)}
                  for y, v, _, _ in measured],
        "volume_figure": fig_json(viz.volume_story(hist.result.to_frame(), {}, {}, measured, today=today)),
    }


@lru_cache(maxsize=1)
def _past_3d() -> dict:
    m = model()
    start = m.hist.result.scenario.start_year
    frames = [(str(int(round(y)) + start), h) for y, h in zip(m.hist.result.snapshot_years, m.hist.result.snapshots)]
    frames = frames[::2] + ([frames[-1]] if (len(frames) - 1) % 2 else [])
    return fig_json(viz.glacier_animation(m.data.grid, m.data.bed, frames, m.data.mask, title="Yala Glacier in ",
                                          h_max=float(m.data.thickness.max())))


def past_3d() -> dict:
    return _past_3d()


def presets() -> dict:
    return {"default": DEFAULT_PRESET, "presets": [
        {"name": n, "notes": c.notes, "warming": c.warming, "precip_pct": int(round(100 * c.precip)), "gradual": c.gradual}
        for n, c in PRESETS.items()]}


def future_results(body: FutureIn) -> dict:
    m = model()
    today, zg = m.today, m.heights
    change, run = future(*body.scenario.key())
    _, base_run = future(0.0, 0, True, body.scenario.key()[3])
    end_year = body.scenario.key()[3]
    label = change.label()
    kept = {}
    for s in body.kept:
        c, r = future(*s.key())
        kept[c.label() if s.key()[3] == end_year else f"{c.label()} (to {s.key()[3]})"] = r
    names = list(kept) + ([label] if label not in kept and label != BASELINE else [])
    colors = viz.assign_colors(names)
    futures = {BASELINE: base_run, **kept}
    if label != BASELINE:
        futures[label] = run

    lead = "If today's climate continues" if label == BASELINE else f"With **{label}**"
    sc = run.scenario
    z = np.arange(4800.0, 6001.0, 10.0)
    end_label = f"{label}, {end_year}"
    profiles = {f"Today ({today})": annual_smb(z, m.hist.present_climate),
                end_label: annual_smb(z, m.hist.present_climate, sc.temp_delta(sc.years), sc.precip_factor(sc.years))}
    return {
        "label": label,
        "is_baseline": label == BASELINE,
        "headline": f"{lead}, Yala Glacier {outcome(run, today, end_year)}.",
        "comparison": None if label == BASELINE else
        f"For comparison: if today's climate simply continues, it {outcome(base_run, today, end_year)} (dashed line).",
        "stats": [
            stat(f"Ice left in {end_year}", f"{run.volume_remaining_pct:.0f} %", None,
                 "loss" if run.volume_remaining_pct < 100 else "gain", f"Compared with the end of {today}."),
            stat(f"Area in {end_year}", f"{run.area[-1] / 1e6:.2f} km²", f"{(run.area[-1] - run.area[0]) / 1e6:+.2f} km²",
                 "loss" if run.area[-1] < run.area[0] else "gain"),
            stat(f"Snowline in {end_year}", f"{run.ela[-1]:,.0f} m", f"{run.ela[-1] - run.ela[0]:+.0f} m",
                 "loss" if run.ela[-1] > run.ela[0] else "gain",
                 f"The top of the glacier is at about {zg.max():,.0f} m. If the snowline rises above it, the glacier "
                 "can no longer gain ice anywhere."),
            stat("Glacier gone by", f"{today + run.year_vanished:.0f}" if run.year_vanished is not None else "still there",
                 None, "loss" if run.year_vanished is not None else "neutral"),
        ],
        "colors": colors,
        "volume_figure": fig_json(viz.volume_story(m.hist.result.to_frame(), {n: r.to_frame() for n, r in futures.items()},
                                                   colors, m.measured_points(), baseline=BASELINE, today=today)),
        "table": [{"scenario": n, "ice_left_pct": round(r.volume_remaining_pct), "end_year": int(today + r.years[-1]),
                   "area_km2": round(r.area[-1] / 1e6, 2), "snowline_rise_m": round(r.ela[-1] - r.ela[0]),
                   "gone_by": None if r.year_vanished is None else int(today + r.year_vanished),
                   "color": viz.INK if n == BASELINE else colors.get(n)}
                  for n, r in futures.items()],
        "series": [series(n, r, today) for n, r in futures.items()],
        "smb_figure": fig_json(viz.smb_profile(z, profiles, {f"Today ({today})": viz.INK,
                                                             end_label: colors.get(label, viz.CATEGORICAL[0])},
                                               (float(zg.min()), float(zg.max())))),
        "snapshot_years": [int(today + round(y)) for y in run.snapshot_years],
    }


@lru_cache(maxsize=32)
def _future_3d(key: tuple) -> dict:
    m = model()
    _, run = future(*key)
    frames = [(str(int(round(y)) + m.today), h) for y, h in zip(run.snapshot_years, run.snapshots)]
    return fig_json(viz.glacier_animation(m.data.grid, m.data.bed, frames, m.data.mask, title="Yala Glacier in ",
                                          h_max=float(m.data.thickness.max())))


def future_3d(scenario: ScenarioIn) -> dict:
    return _future_3d(scenario.key())


def future_maps(year: int, scenario: ScenarioIn) -> dict:
    m = model()
    _, run = future(*scenario.key())
    years = [int(m.today + round(y)) for y in run.snapshot_years]
    year = min(years, key=lambda y: abs(y - year))
    h = run.snapshots[years.index(year)]
    dh = np.where((h >= 1) | (m.hist.present_thickness >= 1), h - m.hist.present_thickness, np.nan)
    return {
        "year": year,
        "thickness_figure": fig_json(viz.field_map(m.data.grid, np.where(h >= 1, h, np.nan), f"Ice thickness in {year}",
                                                   "m", viz.ICE_RAMP, 0, float(m.data.thickness.max()), m.data.mask)),
        "change_figure": fig_json(viz.dh_map(m.data.grid, dh, f"Change since {m.today} (m)", contour_mask=m.data.mask)),
    }


@lru_cache(maxsize=1)
def _stations() -> dict:
    return {s.name: load_aws(s) for s in STATIONS if s.available()}


@lru_cache(maxsize=1)
def _uncorrected_record():
    return load_record(correct_seasons_to_station=False)


def station_summary(hist: HistoryRun, record, stations: dict) -> dict:
    """Model-minus-thermometer statistics for the weather-station check. Only means, never station data, so the
    deploy bundle can carry them (ICIMOD's download terms don't allow passing the data on)."""
    compared = {n: station_comparison(hist, record, r, reanalysis=_uncorrected_record()).dropna(subset=["station_t_c"])
                for n, r in stations.items()}

    def warmer(rows) -> float:
        return float((rows["model_t_c"] - rows["station_t_c"]).mean())

    def monsoon(rows):
        return rows[rows.index.month.isin([6, 7, 8, 9])]

    heights = {s.name: f"{s.elevation:.0f} m" if not s.moves else f"{s.elevation:.0f}/{s.moves[-1][1]:.0f} m"
               for s in STATIONS}
    bc = compared.get(YALA_BASE_CAMP.name)
    on_ice = None
    if YALA_GLACIER.name in stations and YALA_BASE_CAMP.name in stations:
        rates = lapse_rates(stations[YALA_BASE_CAMP.name], stations[YALA_GLACIER.name])
        on_ice = float((rates["t_low"] - rates["t_high"]).mean())
    return {
        "bias": [{"station": f"{n} ({heights[n]})", "year": warmer(c), "monsoon": warmer(monsoon(c))}
                 for n, c in compared.items()],
        "base_camp": None if bc is None else {"year": warmer(bc), "monsoon": warmer(monsoon(bc)), "months": len(bc)},
        "on_ice_colder": on_ice,
    }


@lru_cache(maxsize=1)
def _file_station_summary() -> dict | None:
    stations = _stations()
    return station_summary(model().hist, model().record, stations) if stations else None


def reality() -> dict:
    m = model()
    data, hist, period, record = m.data, m.hist, m.period, m.record
    rc = reality_check(data, hist)
    counts = rc["grade"].value_counts()
    struggles = rc[(rc["grade"] != "matches") & (rc["why_off"] != "")].drop_duplicates("why_off")
    out = {
        "intro": f"A model is only useful if it matches reality. We tuned this one with **a single number**: the average "
                 f"thinning from {period[0]} to {period[1]} seen in the survey maps. Then we compared it with "
                 f"**{len(rc)} other measurements it never saw**, made by scientists on the glacier.",
        "counts": {g: int(counts.get(g, 0)) for g in ("matches", "close", "off")},
        "rows": [{"question": r.question, "measured": r.measured, "model": r.model, "grade": r.grade, "source": r.source}
                 for r in rc.itertuples()],
        "struggles": [{"question": r.question, "why": r.why_off} for r in struggles.itertuples()],
    }

    ymb = yearly_mass_balance(hist, dict(data.site.yearly_mass_balance))
    if len(ymb):
        within = int((abs(ymb["model"] - ymb["measured"]) <= ymb["uncertainty"]).sum())
        out["yearly"] = {
            "figure": fig_json(viz.yearly_mass_balance_chart(ymb)),
            "text": f"Since 2011, scientists have measured how much ice Yala gains or loses each year using stakes drilled "
                    f"into the ice. The model gets the **average** right, but only {within} of {len(ymb)} individual years "
                    f"fall inside the measurement's error bar. It uses monthly weather from a computer reconstruction, not "
                    f"a station on the glacier, so it misses details such as a snowy winter or a sunny summer. That's why "
                    f"its future runs are \"what if\" experiments, not forecasts."}

    tuning = hist.climate.t_annual_ref - ClimateParams.from_record(record, *period).t_annual_ref
    fix = dict(zip(MONTH_NAMES, AWS_MINUS_ERA5LAND))
    lapse_by_month = dict(zip(MONTH_NAMES, KYANJIN_TO_BASE_CAMP_LAPSE))
    gentlest, steepest = min(lapse_by_month, key=lapse_by_month.get), max(lapse_by_month, key=lapse_by_month.get)
    full_name = dict(zip(MONTH_NAMES, calendar.month_name[1:]))
    tuning_text = (f"only had to change the temperature by **{tuning:+.2f} °C**: the model's weather and the real "
                   f"thermometers agree almost without tuning. That is a good sign that its melt rule is sensible, on average."
                   if abs(tuning) < 0.3 else f"had to change the temperature by **{tuning:+.1f} °C**.")
    weather = [
        f"The computer reconstruction of the weather (the *reanalysis*) gets the seasons wrong at Kyanjin: its winters "
        f"are 2–3 °C too cold. So we corrected every month to match the Kyanjing weather station on average "
        f"(January {fix['Jan']:+.1f} °C, July {fix['Jul']:+.1f} °C).",
        f"To get from the village up to the glacier, the model also needs to know how fast the air cools as you climb. "
        f"We measured that too, month by month, between the Kyanjing station and the Yala Base Camp station "
        f"{YALA_BASE_CAMP.elevation - KYANJING.elevation:,.0f} m higher: from {lapse_by_month[gentlest]:.1f} °C per km "
        f"in {full_name[gentlest]} to {lapse_by_month[steepest]:.1f} °C per km in {full_name[steepest]}. In the monsoon "
        f"the air is moist, and rising moist air releases heat as its water vapour condenses, so it cools more slowly. "
        f"With the measured seasons and cooling, tuning the model to the ice loss {tuning_text}",
    ]
    summary = m.stations if m.stations is not None else _file_station_summary()
    if summary:
        out["station_figure"] = fig_json(viz.station_bias_chart(pd.DataFrame(summary["bias"])))
        bc = summary["base_camp"]
        if bc:
            weather.append(
                f"**At Yala Base Camp** ({YALA_BASE_CAMP.elevation:.0f} m, on rock beside the glacier) the model's air is "
                f"{bc['year']:+.1f} °C away from the thermometer over the year and {bc['monsoon']:+.1f} °C in the "
                f"monsoon, when Yala melts, over {bc['months']} months. (Base Camp also helped set the cooling rate, so this "
                f"mostly checks that the pieces fit together.)")
        if summary["on_ice_colder"] is not None:
            weather.append(
                f"**On the glacier itself** the air is {summary['on_ice_colder']:.1f} °C colder than at "
                f"Base Camp, although the station is only about 200–240 m higher. The ice chills the air just above it, "
                f"like the air above a block of ice in a cool box. The model's temperatures describe the air *away* from "
                f"the ice (like at Kyanjin and Base Camp), and its melt rule was set up for that.")
    else:
        weather.append(f"ICIMOD shares the hourly station records for free after registering (Kyanjing "
                       f"doi:{KYANJIN.data_doi}). We haven't yet confirmed that we may pass the data on, so they aren't "
                       f"included here.")
    out["weather"] = weather

    last = max(hist.comparisons)
    out["bands_figure"] = fig_json(viz.band_comparison(hist.comparisons[last], f"{period[0]} → {last}: change at each height"))
    raw = ClimateParams.from_record(record, *period).t_annual_ref
    out["method"] = {
        "grading": "**Matches** = inside the measurement's stated uncertainty (or within 10 % if none is given); "
                   "**close** = within 25 %; **off** = further away.",
        "tuning": f"The weather-record temperature (already corrected to the Kyanjing station's seasons) was raised by "
                  f"{hist.climate.t_annual_ref - raw:+.2f} °C so that the model's {period[0]}–{period[1]} average thinning "
                  f"equals the measured {hist.target_rate:.2f} m per year.",
        "sources": list(dict.fromkeys(rc["source"])),
        "notes": list(data.notes),
    }
    return out


@lru_cache(maxsize=1)
def _learn() -> dict:
    record = model().record
    annual, trend_start = record.annual(), 1981
    clim = record.climatology(1981, 2010)
    html = markdown.markdown(EXPLAINER.read_text(encoding="utf-8"), extensions=["tables"])
    return {
        "explainer_html": html,
        "climate": {
            "intro": f"Glaciers respond to **temperature** (melting) and **precipitation** (snowfall). This is the climate "
                     f"at **{KYANJIN.name}** ({KYANJIN.elevation:.0f} m), the village below Yala Glacier, from "
                     f"{record.first_year} to {record.last_year}.",
            "stats": [
                stat(f"Warming {trend_start}–{record.last_year}",
                     f"{record.trend(trend_start, record.last_year):+.2f} °C", "per decade"),
                stat("Average precipitation", f"{KYANJIN.annual_precip_mm:.0f} mm", "per year"),
                stat("Falls in the monsoon (Jun–Sep)",
                     f"{clim['p_mm'].loc[[6, 7, 8, 9]].sum() / clim['p_mm'].sum():.0%}"),
            ],
            "annual_figure": fig_json(viz.climate_annual_chart(annual, trend_start, record.last_year,
                                                               record.trend(trend_start, record.last_year))),
            "monthly_figure": fig_json(viz.climate_monthly_chart(clim, MONTH_NAMES)),
            "sources": list(record.sources),
        },
    }


def learn() -> dict:
    return _learn()


def warm_up() -> None:
    """Build the glacier, then pre-compute what a class asks for first: every climate idea, a sweep of the temperature
    slider, the 3D history and the reality check. ~1 s per run; afterwards these answer instantly."""
    try:
        model()
        for c in PRESETS.values():
            future(round(c.warming, 1), int(round(100 * c.precip)), c.gradual, 2100)
        _past_3d()
        reality()
        _learn()
        for w in (0.5, 1.0, 2.5, 3.0, 3.5, 5.0):
            future(w, 0, True, 2100)
        log.info("Warm-up finished")
    except Exception:  # never take the server down; requests will compute on demand
        log.exception("Warm-up failed")

