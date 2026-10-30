# CLAUDE.md: HimalSim

A **learning and visualisation** platform for Himalayan glacier and mass-flow simulation. Owner is learning the
physics as the project grows: explain *why* in plain language when changing physics or numerics, and prefer
readable code over clever code. Not research-grade unless explicitly asked; never present outputs as forecasts.

## Terminology (easy to get wrong)
- **DEM = Digital Elevation Model** (input raster of surface heights). It is *not* the simulation method.
- The glacier model is a **Shallow Ice Approximation (SIA)** ice-flow model + **degree-day** surface mass balance (SMB).
- The Rasuwa 2026 event (26 Aug 2026, Bhote Koshi) was a **rock-ice collapse → debris flood**. It needs a separate
  depth-averaged mass-flow model (Voellmy friction), not the glacier code. See ROADMAP.md Phase 3.

## Commands
Python env: Anaconda **base** (`C:\Users\ALiEN\anaconda3\python.exe`, py3.9) has all deps. `glacier_env` lacks pytest. Don't use it.
```bash
python -m pytest                                   # must stay green; ~5 s (+ Yala hindcast if data present)
python -m streamlit run app/streamlit_app.py       # default port 8501; open via http://127.0.0.1:<port>
```
Use `127.0.0.1`, not `localhost`: Chrome has a cached app on `localhost:8765` from another project.
Smoke-test the app headlessly with `streamlit.testing.v1.AppTest` (form submit buttons appear in `at.button`).
Code must stay Python 3.9-compatible (use `from __future__ import annotations`; no `match`, no `X | Y` at runtime).

## Layout
```
himalsim/constants.py         physical constants (SI; time in YEARS)
himalsim/grid.py              Grid (north-up, UTM 45N), read_on_grid / coverage_on_grid / fill_gaps
himalsim/glacier/climate.py   ClimateParams (reference-station climatology), Scenario, PRESET_SCENARIOS
himalsim/glacier/smb.py       annual_smb, equilibrium_line_altitude, calibrate_temperature
himalsim/glacier/flow.py      FlowParams, sia_fluxes (staggered), flux_divergence, limit_outflow, stable_timestep
himalsim/glacier/thickness.py perfect plasticity, volume-area scaling, initial_thickness("scaled")
himalsim/glacier/model.py     simulate() -> RunResult (yearly diagnostics + thickness snapshots)
himalsim/glacier/sites.py     GlacierSite registry (SITES), load_site() -> SiteData; outlines/*.geojson
himalsim/glacier/validation.py geodetic_rate, calibrated_climate, hindcast, band_comparison
himalsim/viz.py               all Plotly figures + colour roles
app/streamlit_app.py          UI only: no physics in here
app/how_it_works.md           in-app explainer; update it whenever physics changes
legacy/                       archived 2025 scripts: never edit or import
```

## Physics & numerics conventions (do not break)
- Units: metres, **years**, SMB in **m ice equivalent / yr** (`WE_TO_ICE` converts from water equivalent).
- Arrays are `(ny, nx)`, row 0 = north. Physics uses index-space differences only, so orientation doesn't matter.
- SIA flux is computed on **cell faces** (Mahaffy scheme). Never compute flux divergence with `np.gradient`
  on cell-centred fluxes; that was the legacy bug and it does not conserve mass.
- `limit_outflow` must be applied before every update: it keeps H ≥ 0 *and* conserves mass. Clipping H alone creates ice.
- Time step is adaptive (`stable_timestep`, dt ≤ cfl·dx²/4D). Never hard-code a fixed dt for flow.
- `accumulation_mask`: new ice may only form inside the glacier outline; outside, SMB is capped at 0.
- Bed = initial surface − estimated thickness. Never use an ice-surface DEM directly as the bed.
- Scenario changes are *relative to the calibrated baseline*; calibration shifts only `t_annual_ref`.

## Data
- DEMs live in `DEM_and_ortho/DEM_and_ortho/` (override with `HIMALSIM_DATA`). **Git-ignored; never commit rasters.**
- `2015Yala_ortho.tif` is **1.6 GB** (7 cm). Never read it whole; use windowed/overview reads.
- DEM facts: all EPSG:32645, nodata −3.4e38. 1981 = 10 m, footprint 4.1 km² (covers more than Yala);
  2007 = 2 m, wide valley coverage (used for surrounding terrain); 2015 = 1 m. Filename suffixes (`_20_-10`) are co-registration shifts.
- Yala outline: RGI60-15.03954 (2.107 km², year 2000) in `himalsim/glacier/outlines/yala_rgi60.geojson` (UTM).
  More outlines: GLIMS WFS `https://www.glims.org/geoserver/ows` layers `GLIMS:RGI_SouthAsiaEast` (RGI6) and
  `GLIMS:RGI2000-v7.0-G-15_south_asia_east_epsg3857` (RGI7). Both return EPSG:3857, so reproject before saving.
  The old glims.org/RGI zip links no longer serve files.

## Reference numbers (regression check after physics changes, 50 m grid)
- Observed thinning over the Yala outline: 1981→2015 −0.54 m/yr, 2007→2015 −0.91 m/yr.
- Calibrated station temperature 3.58 °C, baseline ELA ≈ 5416 m, initial volume 0.094 km³, mean H 45 m.
- Hindcast 1981→2015: glacier-mean Δh model −20.3 m vs observed −18.5 m, band RMSE ≈ 6.6 m, area 2.09→1.86 km².
  Known misfit: upper glacier (>5400 m) thins too much in the model (observed ≈ 0). Needs a snowpack / two-DDF model.
- 100-yr runs: Baseline keeps ~33 % volume; "Paris +1.5 °C" ~1 %; "+4 °C" gone by year ~55. Runtime 1–9 s at 50 m, 10–20× slower at 25 m.
If a change moves these, say so explicitly and explain why.

## Testing rules
- `tests/test_flow.py::test_halfar_dome` (analytical SIA benchmark) and the mass-conservation tests are the guard
  rails for any flow/numerics change. Add a test for every new physics component.
- The Yala hindcast test is skipped automatically when the DEMs are absent.

## Extending
- **New glacier:** add a `GlacierSite` to `SITES` (bounds with ≥1 km margin around the glacier, DEM paths, outline GeoJSON in UTM).
- **New scenario preset:** add to `PRESET_SCENARIOS` with a one-line `notes` explanation for learners.
- **New figure:** put it in `viz.py`. Colours: `CATEGORICAL` in fixed slot order, one slot per scenario, kept for the
  session and never cycled (the app caps stored runs at 8); `ICE_RAMP` for thickness; `DH_DIVERGING` (red = thinning)
  for change; neutral greys for terrain. Never dual y-axes; use stacked panels.
- **Mass-flow module:** goes in `himalsim/massflow/` with its own app page; reuse `grid.py` for DEM handling.

## Working style for this repo
- Explain physics/numerics choices in the PR/summary and in `app/how_it_works.md`, with a citation where one exists.
- Keep `app/` free of physics; keep `himalsim` free of Streamlit.
- Don't commit unless asked. Branch off `main` first.
