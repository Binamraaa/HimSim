# CLAUDE.md: HimalSim

An interactive glacier simulation for **secondary and high-school students** (researchers may enjoy it too).
Two non-negotiables:
1. **The data stays accurate.** Every number shown to students must trace to a cited source or a documented
   calculation. Never invent climate values, glacier facts or thresholds. If unsure, look it up or ask. Record
   provenance in code (`ClimateRecord.sources`, `SiteData.notes`, module docstrings).
2. **Plain language.** UI text and `app/how_it_works.md` are written for ~14–18-year-olds: explain any term the
   first time (DEM, ELA, mass balance), prefer analogies, keep equations in the "advanced" section.

The owner is also learning the physics: explain *why* when changing physics or numerics.

## Terminology
- **DEM = Digital Elevation Model** (a height map). It is *not* the simulation method.
- Glacier model = **Shallow Ice Approximation (SIA)** flow + monthly **degree-day** mass balance (SMB).
- **ELA** = equilibrium-line altitude, shown to students as "snowline".
- The Rasuwa 2026 debris flood is a separate future case study (ROADMAP Phase 3). Out of scope for now.

## Commands
Python env: Anaconda **base** (`C:\Users\ALiEN\anaconda3\python.exe`, py3.9). Keep code 3.9-compatible
(`from __future__ import annotations`; no `match`).
```bash
python -m pytest                                   # 33 tests, ~25 s once cached; must stay green
python -m streamlit run app/streamlit_app.py       # open http://127.0.0.1:8501 (not localhost: a cached app lives there)
python scripts/fetch_kyanjin_climate.py            # rebuild the Kyanjin climate CSV (needs internet)
```
Headless app check: `tests/test_app.py` (`streamlit.testing.v1.AppTest`). Don't use `st.pills`/`st.segmented_control`:
AppTest in Streamlit 1.42 can't drive them (it breaks every later interaction); use `st.radio(horizontal=...)`.
Prepared sites and history runs are cached on disk in `data/cache/` (`himalsim.store.cached`), keyed on the inputs
plus a fingerprint of the package source, so any code change rebuilds them (first load ~10 s, then <1 s).
After replacing DEM files, delete `data/cache/`. 25 m runs are ~6× slower than 50 m.
Network in this environment occasionally drops for a minute; retry before assuming a host is blocked.

## Layout
```
himalsim/constants.py           physical constants (SI; time in YEARS)
himalsim/grid.py                Grid (north-up, UTM 45N), read_on_grid / coverage_on_grid / fill_gaps
himalsim/dem.py                 OPEN_DEMS catalogue, Copernicus GLO-30 reader (+cache), EGM2008 geoid conversion
himalsim/store.py               disk cache for prepared sites / history runs (invalidated by code changes)
himalsim/climate/record.py      ClimateRecord: monthly T/P series, climatology, anomalies, trend, precip rescaling
himalsim/climate/openmeteo.py   Open-Meteo archive API client (ERA5 / ERA5-Land)
himalsim/climate/kyanjin.py     KYANJIN station facts, load_record(), load_icimod_csv() for the real AWS data
himalsim/climate/data/          kyanjin_monthly.csv (versioned; header documents provenance)
himalsim/glacier/climate.py     ClimateParams (.from_record), Scenario (+ observed-year replay), ClimateChange + PRESETS
himalsim/glacier/smb.py         annual_smb, SmbTable (fast SMB(z) lookup), equilibrium_line_altitude, calibrate_temperature
himalsim/glacier/flow.py        FlowParams, sia_fluxes (staggered, active faces, domain), limit_outflow, stable_timestep
himalsim/glacier/thickness.py   perfect plasticity (glacier-only smoothing), volume-area scaling, initial_thickness
himalsim/glacier/model.py       simulate() -> RunResult
himalsim/glacier/sites.py       GlacierSite registry, load_site()/prepare_site() -> SiteData, ice_domain_mask; outlines/
himalsim/glacier/observations.py  Measurement (cited field data + grading rule), YALA_MEASUREMENTS, yearly stake balances
himalsim/glacier/history.py     calibrate(), historical_scenario(), run_history()/prepare_history() -> HistoryRun
himalsim/glacier/validation.py  geodetic_rate, band_comparison, reality_check (model vs every Measurement), yearly_mass_balance
himalsim/viz.py                 all Plotly figures + colour roles
app/streamlit_app.py            UI only; no physics. Guided tabs: 1 Meet Yala · 2 Change the climate · 3 Can we trust it? ·
                                Learn more. Teacher settings in the collapsed sidebar.
app/how_it_works.md             student explainer; update whenever physics changes, and re-verify its numbers
scripts/                        one-off data builders
legacy/                         archived 2025 scripts: never edit or import
```

## Model pipeline (how a run is built)
1. `load_site`: read DEMs → convert to EGM2008 heights → RGI outline mask → terrain from 2007/2015 DEMs, holes from
   Copernicus → initial thickness → bed = surface − thickness → `ice_domain`.
2. `history.calibrate`: base climate = Kyanjin 1981–2015 climatology; shift temperature so the mean SMB over the
   *actual* 1981–2014 years equals the 1981→2015 geodetic rate.
3. `run_history`: replay observed yearly anomalies 1981→2025 from the 1981 surface. The end state = "today".
4. Future scenarios: start from `present_thickness` with `present_climate` (calibrated + 2016–2025 temperature
   anomaly; precipitation kept at the long-term mean because reanalysis precipitation trends are unreliable).
   Students set a `ClimateChange` (warming °C, precipitation %, gradual-to-2100-then-hold or sudden).
5. `reality_check`: grade the model against the site's `measurements` (never used for tuning).

## Physics & numerics conventions (do not break)
- Units: metres, **years**, SMB in **m ice eq. / yr**. Heights in metres above the **EGM2008 geoid**.
- Arrays `(ny, nx)`, row 0 = north; physics uses index-space differences only.
- SIA flux on **cell faces** (Mahaffy). Never compute divergence with `np.gradient` of cell-centred flux.
- A face is active only if its upstream cell has ice and both cells are in `ice_domain`. Inactive faces carry no
  flux and don't limit the time step. `limit_outflow` before every update keeps H ≥ 0 and conserves mass.
- `accumulation_mask` (glacier outline): new ice forms only inside it. `ice_domain`: glacier + connected terrain
  below snout+50 m. Ice can advance down-valley but can't spill over enclosing ridges.
- Initial-thickness smoothing uses **glacier cells only**; terrain beyond the outline must not affect thickness
  (a test enforces this; the bug it prevents doubled the ice at the glacier top).
- Adaptive time step (`stable_timestep`); never a fixed dt for flow.
- SMB inside `simulate` comes from `SmbTable` (exact SMB on a 2 m elevation axis, interpolated): same physics, ~50× faster.

## Data facts
- Yala DEMs: `DEM_and_ortho/DEM_and_ortho/` (override `HIMALSIM_DATA`), **git-ignored**. 1981 = 10 m, 2007 = 2 m
  (wide valley coverage), 2015 = 1 m; nodata −3.4e38; EPSG:32645. `2015Yala_ortho.tif` is 1.6 GB, never read whole.
- **Vertical datum (inferred):** Yala DEMs are WGS84-ellipsoidal. On rock they sit 30.0–31.5 m below Copernicus,
  matching the EGM2008 undulation −31.4 m. `load_site` converts them. Producer confirmation still pending.
- Copernicus GLO-30: `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N28_00_E085_00_DEM/...`,
  no login; cached as .npy in `data/cache/` (git-ignored). Geoid grid comes via PROJ network (cdn.proj.org).
- Kyanjin (3862 m): gauge precipitation **867 mm/yr** at 3857 m (Immerzeel et al. 2014, cited in Steiner et al. 2021,
  doi:10.1002/hyp.14189); monsoon share 70–90 %. Raw ERA5 gives ~1800 mm, so precipitation is rescaled to 867 over
  1981–2010. Temperature = ERA5-Land adjusted to 3862 m. ICIMOD AWS data (registration needed): Kyanjing
  doi:10.26066/RDS.22464, Yala Base Camp RDS.26859, Yala Glacier RDS.1972507. Yala glaciological mass balance at WGMS.
- Field data for the reality check (in `observations.py`, each with DOI): Sugiyama et al. 2013 (radar 2009: volume
  0.061 km³, upper bound 0.066; centre-line thickness at 5120–5300 m 60/45/31 m in 1982/1996/2009; bed frozen in the
  ablation area) and Stumm et al. 2021 (stakes 2011–2017: −0.80 ± 0.28 m w.e./yr, yearly values, ELA 5380–5518 m,
  gradient 1.04 ± 0.12 m w.e./100 m; area 1.61 km² in 2012). Model centre-line equivalent = 75th percentile of
  thickness in the band.
- Outline: RGI60-15.03954 (2.107 km², Nov 2000). GLIMS WFS layers `GLIMS:RGI_SouthAsiaEast` and
  `GLIMS:RGI2000-v7.0-G-15_south_asia_east_epsg3857` return EPSG:3857, so reproject before saving.

## Reference numbers (regression check after changes; 50 m grid, default settings)
- Calibrated station temperature 3.65 °C (ERA5-Land climatology +~1.2 °C); ELA 5428 m (1981–2015) → 5523 m (today).
- Thinning (m/yr), measured vs model: 1981–2007 −0.44 / −0.52; 2007–2015 −0.91 / −0.78; 1981–2015 −0.54 / −0.59.
- 2015 band comparison RMSE ≈ 8.3 m. Known misfit: the tongue (5100–5200 m) thins too much (−64 vs −44 m).
  The upper glacier is close.
- Area 2.09 km² (1981) → 1.75 (2015) → 1.42 (end 2025). Futures from end-2025: today's climate keeps ~25 % of
  the ice to 2100; +1.5 °C by 2100 → gone ~2094; +2 °C → ~2080; +4 °C → ~2060.
- Reality check (standard settings): 6 match, 4 close, 1 off. Matches: volume 2009 (0.061 vs 0.061 km³), centre
  thickness 1982/1996/2009 (60/45/31 vs 59.7/45.5/31.2 m), mean MB 2012–17 (−0.80 vs −0.66), ELA (5380–5518 vs 5470).
  Close: the two thinning rates, area 2006/2012 (model too large: outline definition). Off: SMB gradient (0.77 vs
  1.04). Individual stake years: only 1 of 6 within error (monthly reanalysis forcing).
If a change moves these, say so explicitly and explain why.

## Testing rules
- Halfar dome + mass-conservation tests guard the flow numerics; `test_ice_domain_*` and
  `test_thickness_ignores_terrain_outside_glacier` guard the domain logic; `test_kyanjin_record_matches_station_facts`
  guards the climate data. `test_yala_reality_check` guards the field-data matches; `test_app.py` drives the UI.
Yala tests are skipped when DEMs are absent.
- Add a test for every new physics component or data source.

## Extending
- **New glacier:** `GlacierSite` in `SITES` (bounds ≥1 km beyond the glacier, DEMs, outline GeoJSON in UTM,
  `vertical_datum`). It needs a climate record for its valley too.
- **Real Kyanjin station data:** `kyanjin.load_icimod_csv(path, time_col, temp_col, precip_col)`. Inspect the
  downloaded file's columns first.
- **New field measurement:** a `Measurement` in the site's `measurements` with its DOI; add a model equivalent to
  `validation.MODEL_VALUES` for a new `kind`. Copy uncertainties exactly as the source states them; never invent one.
- **New preset:** `PRESETS` (a `ClimateChange`) with a one-sentence student-friendly `notes`. Describe local warming
  relative to *today*; never label local warming with global targets (e.g. "Paris").
- **Figures:** `viz.py`. `CATEGORICAL` in fixed slot order per scenario (never cycled; the app caps kept runs at 7);
  `INK` for the modelled past and the "today's climate" baseline; 3D views use `glacier_animation` (Play + slider);
  `ICE_RAMP` thickness; `DH_DIVERGING` (red = thinning); neutral greys for terrain; never dual y-axes.

## Working style
- Keep `app/` free of physics and `himalsim` free of Streamlit.
- Don't commit unless asked; Phase 1 work lives on branch `phase1-climate-dem`.
