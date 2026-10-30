"""HimalSim: Yala Glacier explorer for students.

Run with:   python -m streamlit run app/streamlit_app.py

The page is a guided path: 1 · Meet Yala (the past), 2 · Change the climate (the future),
3 · Can we trust it? (the model against real measurements), then Learn more. Teachers'
model settings live in the sidebar, collapsed by default. No physics in this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `himalsim` importable without installing

from himalsim import viz  # noqa: E402
from himalsim.climate.kyanjin import KYANJIN, load_record  # noqa: E402
from himalsim.dem import OPEN_DEMS, geoid_undulation, read_copernicus  # noqa: E402
from himalsim.glacier import PRESETS, SITES, ClimateChange, ClimateParams, FlowParams, prepare_site, simulate  # noqa: E402
from himalsim.glacier.climate import MONTH_NAMES  # noqa: E402
from himalsim.glacier.history import prepare_history  # noqa: E402
from himalsim.glacier.smb import annual_smb, equilibrium_line_altitude  # noqa: E402
from himalsim.glacier.validation import reality_check, yearly_mass_balance  # noqa: E402

SITE = "Yala"  # one glacier for now; more go in himalsim.glacier.sites.SITES
POOL_M3 = 2500.0  # an Olympic swimming pool: 50 m × 25 m × 2 m
GRADUAL, SUDDEN = "Gradually, reaching it in 2100", "All at once, starting now"
GRADE_LABEL = {"matches": "✅ matches", "close": "🟡 close", "off": "❌ off"}
TEACHER_DEFAULTS = {"t_dx": 50.0, "t_lapse": 6.0, "t_pgrad": 5.0, "t_ddf": 8.0,
                    "t_log_a": round(float(np.log10(FlowParams().glen_a)), 2), "t_sliding": False}

st.set_page_config(page_title="HimalSim · Yala Glacier", page_icon="🏔️", layout="wide",
                   initial_sidebar_state="collapsed")
ss = st.session_state
for key, value in {**TEACHER_DEFAULTS, "preset": "+2 °C by 2100", "warming": 2.0, "precip_pct": 0,
                   "mode": GRADUAL, "end_year": 2100, "kept": {}, "colors": {}}.items():
    ss.setdefault(key, value)


# ---------------------------------------------------------------- cached data & model runs
@st.cache_resource(show_spinner="Preparing the glacier (first time only)…")
def get_site(dx: float):
    return prepare_site(SITE, dx)


@st.cache_resource(show_spinner=False)
def get_record():
    return load_record()


@st.cache_resource(show_spinner="Replaying the real weather from 1981 to today (first time only, about 10 s)…")
def get_history(dx: float, base: ClimateParams, flow: FlowParams):
    return prepare_history(get_site(dx), get_record(), flow, base)


@st.cache_resource(show_spinner=False, max_entries=64)
def get_future(dx: float, base: ClimateParams, flow: FlowParams, change: ClimateChange, end_year: int):
    data, hist = get_site(dx), get_history(dx, base, flow)
    scenario = change.scenario(hist.present_year, end_year)
    return simulate(data.bed, hist.present_thickness, dx, hist.present_climate, scenario, flow,
                    accumulation_mask=data.mask, ice_domain=data.ice_domain)


@st.cache_resource(show_spinner=False, max_entries=16)
def past_animation(dx: float, base: ClimateParams, flow: FlowParams):
    data, hist = get_site(dx), get_history(dx, base, flow)
    start = hist.result.scenario.start_year
    frames = [(str(int(round(y)) + start), h) for y, h in zip(hist.result.snapshot_years, hist.result.snapshots)]
    frames = frames[::2] + ([frames[-1]] if (len(frames) - 1) % 2 else [])
    return viz.glacier_animation(data.grid, data.bed, frames, data.mask, title="Yala Glacier in ",
                                 h_max=float(data.thickness.max()))


@st.cache_resource(show_spinner=False, max_entries=32)
def future_animation(dx: float, base: ClimateParams, flow: FlowParams, change: ClimateChange, end_year: int):
    data, hist = get_site(dx), get_history(dx, base, flow)
    run = get_future(dx, base, flow, change, end_year)
    frames = [(str(int(round(y)) + hist.present_year), h) for y, h in zip(run.snapshot_years, run.snapshots)]
    return viz.glacier_animation(data.grid, data.bed, frames, data.mask, title="Yala Glacier in ",
                                 h_max=float(data.thickness.max()))


@st.cache_resource(show_spinner="Downloading Copernicus GLO-30 elevation data…")
def get_copernicus(dx: float):
    grid = get_site(dx).grid
    return read_copernicus(grid), geoid_undulation(grid, SITES[SITE].geoid_fallback)


def million_m3(volume_m3: float) -> str:
    return f"{volume_m3 / 1e6:,.0f} million m³"


# ---------------------------------------------------------------- callbacks
def apply_preset():
    if ss.preset in PRESETS:
        c = PRESETS[ss.preset]
        ss.warming, ss.precip_pct, ss.mode = c.warming, int(round(100 * c.precip)), GRADUAL if c.gradual else SUDDEN


def clear_preset():
    ss.preset = None


def reset_teacher_settings():
    for key, value in TEACHER_DEFAULTS.items():
        ss[key] = value


# ---------------------------------------------------------------- teacher settings (sidebar)
with st.sidebar:
    st.header("For teachers")
    st.caption("The model is set up with standard values from the literature. Changing these re-tunes it and "
               "replays 1981 → today (about 10 s). Students can ignore this panel.")
    st.radio("Grid cell size", [50.0, 25.0], key="t_dx",
             format_func=lambda v: f"{v:.0f} m" + (" (fast)" if v == 50 else " (sharper, ~6× slower)"))
    st.slider("Temperature drop with height (°C per km)", 4.0, 8.0, step=0.1, key="t_lapse",
              help="The lapse rate. 6 °C per km is a typical value for Himalayan valleys.")
    st.slider("Extra precipitation per 100 m of height (%)", 0.0, 20.0, step=0.5, key="t_pgrad")
    st.slider("Melt per degree per day (mm of water)", 3.0, 12.0, step=0.5, key="t_ddf",
              help="The degree-day factor: how much ice melts for each °C above zero, per day.")
    st.slider("Ice softness A (log₁₀ Pa⁻³ s⁻¹)", -25.0, -23.0, step=0.05, key="t_log_a",
              help="Glen's flow-law rate factor. −23.6 is ice at 0 °C; colder ice is stiffer and flows slower.")
    st.toggle("Ice slides on its bed", key="t_sliding",
              help="Drilling found the bed frozen under Yala's lower half (Sugiyama et al. 2013), so sliding is off by default.")
    st.button("Reset to standard values", on_click=reset_teacher_settings)

dx = float(ss.t_dx)
record = get_record()
data = get_site(dx)
period = (data.site.start_year, max(data.observed))
base = ClimateParams.from_record(record, *period, lapse_rate=ss.t_lapse / 1000, p_gradient=ss.t_pgrad / 100,
                                 ddf=ss.t_ddf / 1000)
flow = FlowParams(glen_a=10 ** ss.t_log_a, sliding=5.7e-20 if ss.t_sliding else 0.0)
hist = get_history(dx, base, flow)
today = hist.present_year
past = hist.result.to_frame()
zg = data.observed[period[0]][data.mask]
volume_measurements = [m for m in data.site.measurements if m.kind == "volume"]
measured_points = [(dict(m.params)["year"], m.value, (m.high or m.value) - m.value,
                    f"Measured {dict(m.params)['year']} (radar)") for m in volume_measurements]


# ---------------------------------------------------------------- header
st.title("🏔️ Yala Glacier: its past, and the future you choose")
st.markdown(
    f"Yala is a small glacier high in the Langtang valley, Nepal, between about **{round(zg.min(), -1):,.0f} m and "
    f"{round(zg.max(), -1):,.0f} m** "
    f"above sea level. Scientists have measured it for over 40 years. This simulator replays its real history, then lets "
    f"**you** change the climate and see what happens. Work through the tabs from left to right.")

tabs = st.tabs(["**1 · Meet Yala**", "**2 · Change the climate**", "**3 · Can we trust it?**", "📚 Learn more"])


# ---------------------------------------------------------------- 1. the past
with tabs[0]:
    v0, v_now = hist.result.volume[0], hist.result.volume[-1]
    ela_then, ela_now = equilibrium_line_altitude(hist.climate), equilibrium_line_altitude(hist.present_climate)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Ice in {period[0]}", million_m3(v0), help=f"About {v0 / POOL_M3:,.0f} Olympic swimming pools.")
    c2.metric(f"Ice at the end of {today}", million_m3(v_now), f"{100 * (v_now - v0) / v0:+.0f} %",
              help=f"About {v_now / POOL_M3:,.0f} Olympic swimming pools.")
    c3.metric("Change in snowline height", f"{ela_now - ela_then:+.0f} m", delta_color="off",
              help=f"Average {period[0]}–{period[1]}: {ela_then:,.0f} m. Average {today - 9}–{today}: {ela_now:,.0f} m. "
                   "Above the snowline a glacier gains snow each year; below it, it loses ice.")
    c4.metric(f"{KYANJIN.name} got warmer", f"{hist.recent_warming:+.1f} °C",
              help=f"Average temperature {today - 9}–{today} compared with {period[0]}–{period[1]}.")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.plotly_chart(past_animation(dx, base, flow), use_container_width=True)
    with right:
        st.markdown(
            f"**How do we know?** Scientists mapped the glacier's surface in "
            f"**{', '.join(str(y) for y in sorted(data.observed))}**. The model starts from the {period[0]} map and is fed "
            f"the **weather of every year** since, as reconstructed for {KYANJIN.name} village (see *Learn more*).\n\n"
            f"Press **▶ Play** on the 3D view to watch {today - period[0]} years go by. Drag to turn it around.")
        st.plotly_chart(viz.volume_story(past, {}, {}, measured_points, today=today), use_container_width=True)
        for year, value, _, _ in measured_points:
            model_v = hist.result.volume[year - period[0]]
            st.caption(f"Green diamond: the ice volume measured with radar in {year} ({value * 1000:.0f} million m³). "
                       f"The model never saw it; its own value for {year} is {model_v / 1e6:.0f} million m³.")
    st.success("**Next:** what happens after today depends on the climate. Open **2 · Change the climate**.")


# ---------------------------------------------------------------- 2. the future
with tabs[1]:
    controls, results = st.columns([1, 2.4], gap="large")
    with controls:
        st.markdown("#### Pick an idea…")
        # A radio rather than st.pills: Streamlit 1.42's AppTest can't drive pills, and both read the same.
        st.radio("Ideas", list(PRESETS), key="preset", on_change=apply_preset, label_visibility="collapsed")
        if ss.preset in PRESETS:
            st.caption(PRESETS[ss.preset].notes)
        st.markdown("#### …or set your own")
        st.slider("🌡️ Temperature change (°C)", -2.0, 5.0, step=0.1, key="warming", on_change=clear_preset,
                  help=f"Compared with today's climate (the {today - 9}–{today} average). For scale: Kyanjin warmed "
                       f"{hist.recent_warming:+.1f} °C between {period[0]}–{period[1]} and {today - 9}–{today}.")
        st.slider("🌧️ Change in rain and snow (%)", -50, 50, step=5, key="precip_pct", on_change=clear_preset,
                  help="Positive = wetter, more snow on the glacier. Negative = drier.")
        st.radio("How does the change arrive?", [GRADUAL, SUDDEN], key="mode", on_change=clear_preset)
        with st.expander("More options"):
            st.slider("Run the model until", 2050, 2200, step=10, key="end_year",
                      help="After 2100 the climate stays at its 2100 level, so you can see how long the glacier "
                           "takes to catch up.")

    change = ClimateChange(warming=round(ss.warming, 2), precip=ss.precip_pct / 100, gradual=ss.mode == GRADUAL)
    baseline = ClimateChange()
    end_year = int(ss.end_year)
    run = get_future(dx, base, flow, change, end_year)
    base_run = get_future(dx, base, flow, baseline, end_year)
    label = change.label()

    def outcome(r) -> str:
        if r.year_vanished is not None:
            return f"is gone by about **{today + r.year_vanished:.0f}**"
        return f"keeps **{r.volume_remaining_pct:.0f} %** of today's ice in {end_year}"

    with results:
        lead = "If today's climate continues" if change == baseline else f"With **{label}**"
        st.markdown(f"### {lead}, Yala Glacier {outcome(run)}.")
        if change != baseline:
            st.caption(f"For comparison: if today's climate simply continues, it {outcome(base_run)} (dashed line).")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"Ice left in {end_year}", f"{run.volume_remaining_pct:.0f} %", help="Compared with the end of " + str(today))
        c2.metric(f"Area in {end_year}", f"{run.area[-1] / 1e6:.2f} km²", f"{(run.area[-1] - run.area[0]) / 1e6:+.2f} km²")
        c3.metric(f"Snowline in {end_year}", f"{run.ela[-1]:,.0f} m", f"{run.ela[-1] - run.ela[0]:+.0f} m",
                  delta_color="inverse", help=f"The top of the glacier is at about {zg.max():,.0f} m. If the snowline "
                                              "rises above it, the glacier can no longer gain ice anywhere.")
        c4.metric("Glacier gone by", f"{today + run.year_vanished:.0f}" if run.year_vanished is not None else "still there")

        view_3d, view_chart, view_maps, view_why = st.tabs(["🏔️ 3D view", "📈 Compare", "🗺️ Maps", "❓ Why?"])
        with view_3d:
            st.plotly_chart(future_animation(dx, base, flow, change, end_year), use_container_width=True)
            st.caption("Press ▶ Play. Colours show how thick the ice is.")
        with view_chart:
            names = list(ss.kept) + ([label] if label not in ss.kept and change != baseline else [])
            ss.colors = viz.assign_colors(names, {k: v for k, v in ss.colors.items() if k in names})
            futures = {"Today's climate continues": base_run.to_frame()}
            futures.update({n: get_future(dx, base, flow, c, e).to_frame() for n, (c, e) in ss.kept.items()})
            futures[label] = run.to_frame()
            st.plotly_chart(viz.volume_story(past, futures, ss.colors, measured_points,
                                             baseline="Today's climate continues", today=today),
                            use_container_width=True)
            b1, b2 = st.columns(2)
            if b1.button("📌 Keep this result to compare", use_container_width=True,
                         disabled=label in ss.kept or change == baseline or len(ss.kept) >= len(viz.CATEGORICAL) - 1):
                ss.kept[label] = (change, end_year)
                st.rerun()
            if b2.button("Clear kept results", use_container_width=True, disabled=not ss.kept):
                ss.kept = {}
                st.rerun()
            rows = {"Today's climate continues": base_run, **{n: get_future(dx, base, flow, c, e) for n, (c, e) in ss.kept.items()},
                    label: run}
            st.dataframe(pd.DataFrame([{
                "Scenario": n, f"Ice left in {today + int(r.years[-1])} (%)": round(r.volume_remaining_pct),
                "Area (km²)": round(r.area[-1] / 1e6, 2), "Snowline rise (m)": round(r.ela[-1] - r.ela[0]),
                "Gone by": "still there" if r.year_vanished is None else str(int(today + r.year_vanished)),
            } for n, r in rows.items()]), hide_index=True, use_container_width=True)
            frame = pd.concat([r.to_frame().assign(scenario=n) for n, r in rows.items()], ignore_index=True)
            st.download_button("⬇ Download these results (CSV)", frame.to_csv(index=False), "yala_scenarios.csv", "text/csv")
        with view_maps:
            snap_years = [today + int(round(y)) for y in run.snapshot_years]
            year = st.select_slider("Year", options=snap_years, value=snap_years[-1])
            h = run.snapshots[snap_years.index(year)]
            m1, m2 = st.columns(2)
            m1.plotly_chart(viz.field_map(data.grid, np.where(h >= 1, h, np.nan), f"Ice thickness in {year}", "m",
                                          viz.ICE_RAMP, 0, float(data.thickness.max()), data.mask), use_container_width=True)
            dh = np.where((h >= 1) | (hist.present_thickness >= 1), h - hist.present_thickness, np.nan)
            m2.plotly_chart(viz.dh_map(data.grid, dh, f"Change since {today} (m)", contour_mask=data.mask),
                            use_container_width=True)
            st.caption("Black line: the glacier outline in 2000. Red = the ice got thinner, blue = thicker.")
        with view_why:
            st.markdown(
                "Every year, snow falls on the glacier and some ice melts. Where more snow falls than melts, the glacier "
                "grows; where more melts, it shrinks. The height where the two balance is the **snowline** (scientists say "
                "*equilibrium-line altitude*, ELA). The lines below show the yearly gain (right of zero) or loss (left of "
                "zero) at each height. Warmer air pushes the line left and the snowline up.")
            z = np.arange(4800.0, 6001.0, 10.0)
            sc = run.scenario
            end_label = f"{label}, {end_year}"
            profiles = {f"Today ({today})": annual_smb(z, hist.present_climate),
                        end_label: annual_smb(z, hist.present_climate, sc.temp_delta(sc.years), sc.precip_factor(sc.years))}
            colors = {f"Today ({today})": viz.INK, end_label: ss.colors.get(label, viz.CATEGORICAL[0])}
            st.plotly_chart(viz.smb_profile(z, profiles, colors, (float(zg.min()), float(zg.max()))), use_container_width=True)
            st.caption("Grey band: the heights the glacier covers. If the snowline climbs above the band, the glacier has "
                       "nowhere left to gain ice and will disappear, even if that takes decades.")


# ---------------------------------------------------------------- 3. reality check
with tabs[2]:
    rc = reality_check(data, hist)
    n = rc["grade"].value_counts()
    st.markdown(
        f"A model is only useful if it matches reality. We tuned this one with **a single number**: the average "
        f"thinning from {period[0]} to {period[1]} seen in the survey maps. Then we compared it with "
        f"**{len(rc)} other measurements it never saw**, made by scientists on the glacier.")
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Matches", int(n.get("matches", 0)), help="Within the measurement's stated uncertainty, or within 10 %.")
    c2.metric("🟡 Close", int(n.get("close", 0)), help="Within 25 % of the measured value.")
    c3.metric("❌ Off", int(n.get("off", 0)), help="More than 25 % away from the measured value.")
    st.dataframe(rc.assign(grade=rc["grade"].map(GRADE_LABEL))[["question", "measured", "model", "grade"]],
                 hide_index=True, use_container_width=True,
                 column_config={"question": st.column_config.TextColumn("What was measured", width="large"),
                                "measured": "Measured", "model": "Model", "grade": "Result"})
    struggles = rc[(rc["grade"] != "matches") & (rc["why_off"] != "")].drop_duplicates("why_off")
    if len(struggles):
        st.markdown("**Where the model struggles, and why**\n" +
                    "\n".join(f"- *{r.question}* {r.why_off}" for r in struggles.itertuples()))

    st.subheader("Good years and bad years")
    ymb = yearly_mass_balance(hist, dict(data.site.yearly_mass_balance))
    if len(ymb):
        within = int((abs(ymb["model"] - ymb["measured"]) <= ymb["uncertainty"]).sum())
        st.plotly_chart(viz.yearly_mass_balance_chart(ymb), use_container_width=True)
        st.caption(
            f"Since 2011, scientists have measured how much ice Yala gains or loses each year using stakes drilled into the "
            f"ice. The model gets the **average** right, but only {within} of {len(ymb)} individual years fall inside the "
            f"measurement's error bar. It uses monthly weather from a computer reconstruction, not a station on the glacier, "
            f"so it misses details such as a snowy winter or a sunny summer. That's why its future runs are \"what if\" "
            f"experiments, not forecasts.")

    with st.expander("Where on the glacier did the ice thin? (survey maps)"):
        cols = st.columns(len(hist.comparisons))
        for col, (year, df) in zip(cols, hist.comparisons.items()):
            col.plotly_chart(viz.band_comparison(df, f"{period[0]} → {year}: change at each height"), use_container_width=True)
        last = max(hist.comparisons)
        snap = hist.result.snapshots[[int(round(y)) for y in hist.result.snapshot_years].index(last - period[0])]
        start_surface = data.observed[period[0]]
        m1, m2 = st.columns(2)
        m1.plotly_chart(viz.dh_map(data.grid, np.where(data.mask, data.observed[last] - start_surface, np.nan),
                                   f"Measured change {period[0]} → {last} (m)", contour_mask=data.mask), use_container_width=True)
        m2.plotly_chart(viz.dh_map(data.grid, np.where(data.mask, data.bed + snap - start_surface, np.nan),
                                   f"Model change {period[0]} → {last} (m)", contour_mask=data.mask), use_container_width=True)
        st.caption("The model thins the lowest part of the glacier (the tongue) a little too much and gets the upper part "
                   "about right.")
    with st.expander("How we graded, and where the measurements come from"):
        raw = ClimateParams.from_record(record, *period).t_annual_ref
        st.markdown(
            "**Grading:** ✅ *matches* = inside the measurement's stated uncertainty (or within 10 % if none is given); "
            "🟡 *close* = within 25 %; ❌ *off* = further away.\n\n"
            f"**Tuning:** the weather-record temperature was raised by {hist.climate.t_annual_ref - raw:+.2f} °C so that the "
            f"model's {period[0]}–{period[1]} average thinning equals the measured {hist.target_rate:.2f} m per year. "
            "Reanalysis temperatures in steep Himalayan valleys are often a degree or two too cold.\n\n**Sources:**\n" +
            "\n".join(f"- {s}" for s in dict.fromkeys(rc["source"])) +
            "\n\n**How the model glacier was built:**\n" + "\n".join(f"- {note}" for note in data.notes))


# ---------------------------------------------------------------- 4. learn more
with tabs[3]:
    learn_how, learn_climate, learn_dem = st.tabs(["How the model works", "Climate data", "Elevation maps (DEMs)"])
    with learn_how:
        st.markdown(Path(__file__).with_name("how_it_works.md").read_text(encoding="utf-8"))

    with learn_climate:
        annual = record.annual()
        trend_start = 1981
        st.markdown(
            f"Glaciers respond to **temperature** (melting) and **precipitation** (snowfall). This is the climate at "
            f"**{KYANJIN.name}** ({KYANJIN.elevation:.0f} m), the village below Yala Glacier, from {record.first_year} "
            f"to {record.last_year}.")
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Warming {trend_start}–{record.last_year}", f"{record.trend(trend_start, record.last_year):+.2f} °C per decade")
        c2.metric("Average precipitation", f"{KYANJIN.annual_precip_mm:.0f} mm/yr")
        clim = record.climatology(1981, 2010)
        c3.metric("Falls in the monsoon (Jun–Sep)", f"{clim['p_mm'].loc[[6, 7, 8, 9]].sum() / clim['p_mm'].sum():.0%}")
        st.plotly_chart(viz.climate_annual_chart(annual, trend_start, record.last_year,
                                                 record.trend(trend_start, record.last_year)), use_container_width=True)
        st.subheader("An average year (1981–2010)")
        st.plotly_chart(viz.climate_monthly_chart(clim, MONTH_NAMES), use_container_width=True)
        with st.expander("Where do these numbers come from? (and why it matters)"):
            st.markdown(
                f"""
- **Temperature:** the ERA5-Land *reanalysis*, a computer reconstruction of past weather built from millions of
  observations, adjusted to the height of Kyanjin. It has no gaps, which real stations almost always do.
- **Precipitation:** the ERA5 reanalysis gives the **pattern** (which months and years were wetter), but it says about
  **1800 mm** falls at Kyanjin each year, roughly double what the rain gauge there measures (**{KYANJIN.annual_precip_mm:.0f} mm**,
  Immerzeel et al. 2014). Global models struggle with rain in steep Himalayan valleys. So we keep the pattern and scale
  the amount to match the gauge. Scientists call this *bias correction*.
- **The real station:** the Kyanjing weather station (run by DHM Nepal, ICIMOD and Utrecht University) shares its data
  openly after a free registration: doi:{KYANJIN.data_doi}.

Sources:
""" + "\n".join(f"- {s}" for s in record.sources))
        st.download_button("⬇ Download the monthly climate record (CSV)", record.data.to_csv(), "kyanjin_monthly.csv", "text/csv")

    with learn_dem:
        st.markdown(
            "A **DEM (Digital Elevation Model)** is a map where every pixel stores a height. Glacier scientists compare "
            "DEMs from different years to see how much ice was lost. Here are the free DEMs that cover the whole Himalaya:")
        st.dataframe(pd.DataFrame([{
            "DEM": d.name, "Pixel size": d.resolution, "When": d.epoch, "How it was made": d.method,
            "Height measured from": d.vertical_datum, "How to get it": d.access, "Licence": d.licence,
            "For glaciers": d.glacier_notes,
        } for d in OPEN_DEMS]), hide_index=True, use_container_width=True)

        st.subheader("Experiment: compare a free global DEM with the Yala survey")
        dem_year = st.radio("Yala DEM", sorted(data.observed), index=len(data.observed) - 1, horizontal=True)
        try:
            cop, geoid = get_copernicus(dx)
        except Exception as exc:  # offline
            st.warning(f"Couldn't download Copernicus GLO-30 ({type(exc).__name__}). Check the internet connection.")
        else:
            diff = cop - data.observed[dem_year]
            stable = ~data.mask & np.isfinite(diff)
            on_ice = data.mask & np.isfinite(diff)
            raw_offset = float(np.median((diff - geoid)[stable]))
            c1, c2, c3 = st.columns(3)
            c1.metric("Before datum correction (rock)", f"{raw_offset:+.1f} m")
            c2.metric("After datum correction (rock)", f"{np.median(diff[stable]):+.1f} m")
            c3.metric("On the glacier", f"{np.median(diff[on_ice]):+.1f} m")
            st.plotly_chart(viz.dh_map(data.grid, np.where(np.isfinite(data.observed[dem_year]), diff, np.nan),
                                       f"Copernicus GLO-30 (2011–2015) minus Yala DEM {dem_year}", limit=30,
                                       contour_mask=data.mask), use_container_width=True)
            st.markdown(
                f"""
**What's going on?**
1. **The 31 m puzzle.** At first the two maps disagreed by about {raw_offset:.0f} m everywhere, even on solid rock.
   They measure height from different "zero levels". The Yala DEMs use the **ellipsoid**, a smooth mathematical shape
   of the Earth used by GPS. Copernicus uses the **geoid**, roughly mean sea level. Here the geoid lies
   {-geoid.mean():.1f} m below the ellipsoid. After correcting for this, rock agrees to within about a metre.
2. **On the glacier the maps still differ.** Copernicus was measured in 2011–2015, so compared with older Yala maps the
   glacier surface is lower (red). The ice really thinned.
3. **Pixel size matters.** Copernicus pixels are 30 m wide; the 2015 Yala survey resolves 1 m. Sharp ridges and
   crevasses get smoothed in coarser maps, which shows up as speckle along steep slopes.
""")
