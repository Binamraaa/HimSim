"""HimalSim glacier scenario lab.

Run with:   streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `himalsim` importable without installing

from himalsim import viz  # noqa: E402
from himalsim.glacier import PRESET_SCENARIOS, SITES, ClimateParams, FlowParams, Scenario, load_site, simulate  # noqa: E402
from himalsim.glacier.smb import annual_smb, equilibrium_line_altitude  # noqa: E402
from himalsim.glacier.validation import calibrated_climate, geodetic_rate, hindcast  # noqa: E402

MAX_RUNS = len(viz.CATEGORICAL)  # one colour per stored run; never cycle colours

st.set_page_config(page_title="HimalSim · Glacier scenarios", page_icon="🏔️", layout="wide")


# ---------------------------------------------------------------- cached data
@st.cache_resource(show_spinner="Loading DEMs and building the model grid…")
def get_site(name: str, dx: float):
    return load_site(SITES[name], dx=dx)


@st.cache_data(show_spinner=False)
def get_calibrated(name: str, dx: float, base: ClimateParams):
    return calibrated_climate(get_site(name, dx), base)


@st.cache_data(show_spinner="Running 1981→2015 hindcast…")
def get_hindcast(name: str, dx: float, climate: ClimateParams, flow: FlowParams):
    return hindcast(get_site(name, dx), climate, flow)


ss = st.session_state
ss.setdefault("runs", {})  # scenario name -> RunResult (insertion-ordered)
ss.setdefault("colors", {})  # scenario name -> hex; a scenario keeps its colour for the session


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Model setup")
    site_name = st.selectbox("Glacier", list(SITES), help=SITES[next(iter(SITES))].description)
    dx = st.radio("Grid resolution", [50.0, 25.0], format_func=lambda v: f"{v:.0f} m" + (" (fast)" if v == 50 else " (detailed, ~10× slower)"),
                  horizontal=False)

    with st.expander("Baseline climate", expanded=False):
        st.caption("Reference station: Kyanjin Gompa, 3862 m. Defaults are approximate Langtang values.")
        base = ClimateParams()
        base = replace(
            base,
            lapse_rate=st.slider("Lapse rate (°C per km)", 4.0, 8.0, base.lapse_rate * 1000, 0.1) / 1000,
            t_seasonal_amp=st.slider("Seasonal temperature amplitude (°C)", 3.0, 12.0, base.t_seasonal_amp, 0.5),
            p_annual_ref=st.slider("Annual precipitation at station (m w.e.)", 0.2, 2.0, base.p_annual_ref, 0.05),
            p_gradient=st.slider("Precipitation increase per 100 m (%)", 0.0, 20.0, base.p_gradient * 100, 0.5) / 100,
            monsoon_fraction=st.slider("Share of precipitation in monsoon (Jun–Sep)", 0.4, 0.95, base.monsoon_fraction, 0.05),
            ddf=st.slider("Degree-day factor (mm w.e. per °C per day)", 3.0, 12.0, base.ddf * 1000, 0.5) / 1000,
        )
        calibrate = st.toggle("Calibrate temperature to observed thinning", value=True,
                              help="Shifts the station temperature so the modelled glacier-wide mass balance equals the "
                                   "1981→2015 DEM-differenced thinning rate.")
        if not calibrate:
            base = replace(base, t_annual_ref=st.slider("Annual mean temperature at station (°C)", -5.0, 10.0, base.t_annual_ref, 0.1))

    with st.expander("Ice flow", expanded=False):
        log_a = st.slider("Ice softness A (log₁₀ Pa⁻³ s⁻¹)", -25.0, -23.0, float(np.log10(FlowParams().glen_a)), 0.05,
                          help="Glen's rate factor. −23.6 is temperate ice; colder ice is stiffer (more negative).")
        sliding_on = st.toggle("Basal sliding", value=False, help="Oerlemans (1997) sliding law with f_s = 5.7e-20 Pa⁻³ m² s⁻¹.")
        flow = FlowParams(glen_a=10**log_a, sliding=5.7e-20 if sliding_on else 0.0)

data = get_site(site_name, dx)
if calibrate:
    climate, target_rate = get_calibrated(site_name, dx, base)
else:
    climate, target_rate = base, geodetic_rate(data, data.site.start_year, max(data.observed))
cell_area = data.grid.cell_area
ela0 = equilibrium_line_altitude(climate)

with st.sidebar:
    st.divider()
    st.metric("Station temperature used", f"{climate.t_annual_ref:.2f} °C")
    st.metric("Baseline ELA", f"{ela0:.0f} m")
    st.caption(f"Observed thinning {data.site.start_year}→{max(data.observed)}: {target_rate:.2f} m/yr")


# ---------------------------------------------------------------- header
st.title(f"🏔️ {data.site.name} Glacier: scenario lab")
st.caption(f"{data.site.description}  ·  Start state: {data.site.start_year} DEM  ·  "
           f"Glacier area {data.mask.sum() * cell_area / 1e6:.2f} km²  ·  "
           f"Initial volume {data.thickness.sum() * cell_area / 1e9:.3f} km³  ·  "
           f"Mean thickness {data.thickness[data.mask].mean():.0f} m")

tab_lab, tab_compare, tab_smb, tab_valid, tab_learn = st.tabs(
    ["🧪 Scenario lab", "📈 Compare scenarios", "❄️ Mass balance", "✅ Validation 1981→2015", "📘 How it works"])


# ---------------------------------------------------------------- scenario lab
with tab_lab:
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.subheader("Define a scenario")
        preset_name = st.selectbox("Start from a preset", list(PRESET_SCENARIOS) + ["Custom"])
        preset = PRESET_SCENARIOS.get(preset_name, Scenario(name="Custom"))
        if preset.notes:
            st.caption(preset.notes)
        with st.form("scenario_form"):
            k = preset_name  # widget keys tied to the preset, so switching presets refreshes the defaults
            name = st.text_input("Scenario name", preset.name, key=f"name_{k}")
            years = st.slider("Years to simulate", 10, 300, preset.years, 5, key=f"years_{k}")
            st.markdown("**Temperature**")
            temp_offset = st.slider("Immediate change (°C)", -3.0, 5.0, preset.temp_offset, 0.1, key=f"toff_{k}")
            temp_trend = st.slider("Warming rate (°C per decade)", -0.5, 1.0, preset.temp_trend, 0.01, key=f"ttr_{k}")
            st.markdown("**Precipitation**")
            precip_change = st.slider("Immediate change (%)", -50, 50, int(round(preset.precip_change * 100)), 5, key=f"poff_{k}")
            precip_trend = st.slider("Trend (% per decade)", -10.0, 10.0, preset.precip_trend * 100, 0.5, key=f"ptr_{k}")
            submitted = st.form_submit_button("▶ Run scenario", type="primary", use_container_width=True)

        if submitted:
            scenario = Scenario(name=name.strip() or "Unnamed", years=years, temp_offset=temp_offset, temp_trend=temp_trend,
                                precip_change=precip_change / 100, precip_trend=precip_trend / 100, notes=preset.notes)
            bar = st.progress(0.0, text="Simulating…")
            result = simulate(data.bed, data.thickness, dx, climate, scenario, flow, accumulation_mask=data.mask,
                              progress=lambda f: bar.progress(f, text=f"Simulating… year {f * years:.0f}/{years}"))
            bar.empty()
            ss.runs.pop(scenario.name, None)
            ss.runs[scenario.name] = result
            while len(ss.runs) > MAX_RUNS:
                oldest = next(iter(ss.runs))
                ss.runs.pop(oldest)
                ss.colors.pop(oldest, None)
            ss.colors = viz.assign_colors(list(ss.runs), ss.colors)
            ss["shown_run"] = scenario.name

    with right:
        if not ss.runs:
            st.subheader(f"Starting state ({data.site.start_year})")
            st.plotly_chart(viz.glacier_3d(data.grid, data.bed, data.thickness), use_container_width=True)
            st.info("Pick a preset or set your own temperature and precipitation changes, then press **Run scenario**.")
        else:
            names = list(ss.runs)
            shown = st.selectbox("Show run", names, index=names.index(ss.get("shown_run", names[-1])) if ss.get("shown_run") in names else len(names) - 1)
            res = ss.runs[shown]
            vanished = res.year_vanished
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Volume left", f"{res.volume_remaining_pct:.0f} %")
            c2.metric("Area", f"{res.area[-1] / 1e6:.2f} km²", f"{(res.area[-1] - res.area[0]) / 1e6:+.2f} km²")
            c3.metric("ELA", f"{res.ela[-1]:.0f} m", f"{res.ela[-1] - res.ela[0]:+.0f} m", delta_color="inverse")
            c4.metric("Glacier gone by", f"year {vanished:.0f}" if vanished is not None else "survives")

            snap_years = [int(round(y)) for y in res.snapshot_years]
            year = st.select_slider("Year", options=snap_years, value=snap_years[-1])
            h = res.snapshots[snap_years.index(year)]
            st.plotly_chart(
                viz.glacier_3d(data.grid, data.bed, h, title=f"{shown}: year {year}",
                               h_max=float(max(s.max() for s in res.snapshots))),
                use_container_width=True)
            m1, m2 = st.columns(2)
            with m1:
                st.plotly_chart(viz.field_map(data.grid, np.where(h >= 1, h, np.nan), "Ice thickness", "m",
                                              viz.ICE_RAMP, 0, None, data.mask), use_container_width=True)
            with m2:
                dh = np.where((h >= 1) | data.mask, h - data.thickness, np.nan)
                st.plotly_chart(viz.dh_map(data.grid, dh, f"Thickness change since start (year {year})",
                                           contour_mask=data.mask), use_container_width=True)
            st.caption("Black line = initial glacier outline (RGI 6.0). Red = thinning, blue = thickening.")


# ---------------------------------------------------------------- compare
with tab_compare:
    if not ss.runs:
        st.info("Run at least one scenario in the Scenario lab.")
    else:
        frame = pd.concat([r.to_frame() for r in ss.runs.values()], ignore_index=True)
        st.plotly_chart(viz.scenario_timeseries(frame, ss.colors), use_container_width=True)
        summary = pd.DataFrame([{
            "Scenario": n,
            "Years": r.scenario.years,
            "ΔT now (°C)": r.scenario.temp_offset,
            "Warming (°C/decade)": r.scenario.temp_trend,
            "ΔP (%)": 100 * r.scenario.precip_change,
            "Volume left (%)": round(r.volume_remaining_pct, 1),
            "Final area (km²)": round(r.area[-1] / 1e6, 2),
            "ELA change (m)": round(r.ela[-1] - r.ela[0]),
            "Gone by year": r.year_vanished,
        } for n, r in ss.runs.items()])
        st.dataframe(summary, hide_index=True, use_container_width=True)
        d1, d2 = st.columns(2)
        d1.download_button("⬇ Download time series (CSV)", frame.to_csv(index=False), "himalsim_scenarios.csv", "text/csv")
        if d2.button("🗑 Clear all runs"):
            ss.runs, ss.colors = {}, {}
            st.rerun()


# ---------------------------------------------------------------- mass balance
with tab_smb:
    st.markdown("Surface mass balance against elevation. Above the **ELA** (where a line crosses zero) the glacier "
                "gains ice; below it the glacier loses ice. Warming moves the curve left and the ELA up.")
    z = np.arange(4500.0, 6501.0, 10.0)
    profiles = {"Baseline climate": annual_smb(z, climate)}
    colors = {"Baseline climate": "#52514e"}
    for n, r in ss.runs.items():
        sc = r.scenario
        label = f"{n} (year {sc.years})"
        profiles[label] = annual_smb(z, climate, sc.temp_delta(sc.years), sc.precip_factor(sc.years))
        colors[label] = ss.colors[n]
    zg = data.surface[data.mask]
    st.plotly_chart(viz.smb_profile(z, profiles, colors, (float(zg.min()), float(zg.max()))), use_container_width=True)


# ---------------------------------------------------------------- validation
with tab_valid:
    st.markdown(
        f"Does the model reproduce reality? Starting from the **{data.site.start_year}** surface with the baseline climate, "
        f"the model runs forward and is compared with the DEMs from later years. The calibration only matched the "
        f"glacier-wide *average* thinning, so the **pattern** by elevation is an independent test.")
    if st.button("Run hindcast", type="primary"):
        ss["show_hindcast"] = True
    if ss.get("show_hindcast"):
        res, comps = get_hindcast(site_name, dx, climate, flow)
        last_year = max(comps)
        cols = st.columns(len(comps))
        for col, (year, df) in zip(cols, comps.items()):
            w = df["cells"]
            obs, mod = np.average(df["observed_dh"], weights=w), np.average(df["modeled_dh"], weights=w)
            rmse = float(np.sqrt(np.average((df["observed_dh"] - df["modeled_dh"]) ** 2, weights=w)))
            with col:
                st.plotly_chart(viz.band_comparison(df, f"{data.site.start_year} → {year}"), use_container_width=True)
                st.caption(f"Glacier-mean Δh: observed **{obs:+.1f} m**, model **{mod:+.1f} m** · band RMSE **{rmse:.1f} m**")
        idx = int(np.argmin(np.abs(np.array(res.snapshot_years) - (last_year - data.site.start_year))))
        start = data.observed[data.site.start_year]
        obs_dh = np.where(data.mask, data.observed[last_year] - start, np.nan)
        mod_dh = np.where(data.mask, data.bed + res.snapshots[idx] - start, np.nan)
        m1, m2 = st.columns(2)
        m1.plotly_chart(viz.dh_map(data.grid, obs_dh, f"Observed Δh {data.site.start_year}→{last_year}", contour_mask=data.mask), use_container_width=True)
        m2.plotly_chart(viz.dh_map(data.grid, mod_dh, f"Modelled Δh {data.site.start_year}→{last_year}", contour_mask=data.mask), use_container_width=True)
        st.caption("Try changing the precipitation gradient or degree-day factor in the sidebar and re-running. "
                   "Can you make the upper glacier match better without spoiling the tongue?")


# ---------------------------------------------------------------- explainer
with tab_learn:
    st.markdown(Path(__file__).with_name("how_it_works.md").read_text(encoding="utf-8"))
