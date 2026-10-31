# CLAUDE.md: HimSim

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
- Glacier model = **Shallow Ice Approximation (SIA)** flow + monthly **degree-day** mass balance (SMB) with separate
  snow/ice degree-day factors and a monthly snowpack (balance year from 1 October).
- **ELA** = equilibrium-line altitude, shown to students as "snowline".
- The Rasuwa 2026 debris flood is a separate future case study (ROADMAP Phase 3). Out of scope for now.

## Commands
Python env: Anaconda **base** (`C:\Users\ALiEN\anaconda3\python.exe`, py3.9). Keep code 3.9-compatible
(`from __future__ import annotations`; no `match`).
```bash
python -m pytest                                   # 49 tests, ~80 s once cached; must stay green
python -m streamlit run app/streamlit_app.py       # open http://127.0.0.1:8501 (not localhost: a cached app lives there)
python scripts/fetch_kyanjin_climate.py            # rebuild the Kyanjin climate CSV (needs internet)
```
Headless app check: `tests/test_app.py` (`streamlit.testing.v1.AppTest`). Don't use `st.pills`/`st.segmented_control`:
AppTest in Streamlit 1.42 can't drive them (it breaks every later interaction); use `st.radio(horizontal=...)`.
Prepared sites and history runs are cached on disk in `data/cache/` (`himsim.store.cached`), keyed on the inputs
plus a fingerprint of the package source, so any code change rebuilds them (first load ~10 s, then <1 s).
After replacing DEM files, delete `data/cache/`. 25 m runs are ~6× slower than 50 m.
Network in this environment occasionally drops for a minute; retry before assuming a host is blocked.

## Layout
```
himsim/constants.py           physical constants (SI; time in YEARS)
himsim/grid.py                Grid (north-up, UTM 45N), read_on_grid / coverage_on_grid / fill_gaps
himsim/dem.py                 OPEN_DEMS catalogue, Copernicus GLO-30 reader (+cache), EGM2008 geoid conversion
himsim/store.py               disk cache for prepared sites / history runs (invalidated by code changes)
himsim/climate/record.py      ClimateRecord: monthly T/P series, climatology, anomalies, trend, precip rescaling,
                              per-calendar-month temperature offsets, optional monthly_lapse (°C/m)
himsim/climate/openmeteo.py   Open-Meteo archive API client (ERA5 / ERA5-Land)
himsim/climate/kyanjin.py     KYANJIN facts, load_record() (+ AWS_MINUS_ERA5LAND seasonal correction,
                              KYANJIN_TO_BASE_CAMP_LAPSE monthly lapse rates), load_kyanjing_aws()
himsim/climate/icimod_aws.py  AwsStation registry (Kyanjing, Yala Base Camp, Yala Glacier), read_aws, known faults,
                              aws_monthly (QC), load_aws, lapse_rates, radiation_inputs (SW_in, albedo, daily T spread)
himsim/climate/data/          kyanjin_monthly.csv (versioned; header documents provenance)
himsim/glacier/climate.py     ClimateParams (.from_record), Scenario (+ observed-year replay), ClimateChange + PRESETS
himsim/glacier/smb.py         annual_smb (snowpack: snow melts first, then ice), melt_rates ("ti" degree days or "eti"
                              + sunshine), SmbTable (fast SMB(z) lookup), equilibrium_line_altitude, calibrate_temperature
himsim/glacier/flow.py        FlowParams, sia_fluxes (staggered, active faces, domain), limit_outflow, stable_timestep
himsim/glacier/thickness.py   perfect plasticity (glacier-only smoothing), volume-area scaling, initial_thickness
himsim/glacier/model.py       simulate() -> RunResult
himsim/glacier/sites.py       GlacierSite registry, load_site()/prepare_site() -> SiteData, ice_domain_mask; outlines/
himsim/glacier/observations.py  Measurement (cited field data + grading rule), YALA_MEASUREMENTS, yearly stake balances
himsim/glacier/history.py     calibrate(), historical_scenario(), run_history()/prepare_history() -> HistoryRun
himsim/glacier/validation.py  geodetic_rate, band_comparison, reality_check (model vs every Measurement), yearly_mass_balance
himsim/viz.py                 all Plotly figures + colour roles
app/streamlit_app.py            UI only; no physics. Guided tabs: 1 Meet Yala · 2 Change the climate · 3 Can we trust it? ·
                                Learn more. Teacher settings in the collapsed sidebar.
app/how_it_works.md             student explainer; update whenever physics changes, and re-verify its numbers
scripts/                        one-off data builders
legacy/                         archived 2025 scripts: never edit or import
```

## Model pipeline (how a run is built)
1. `load_site`: read DEMs → convert to EGM2008 heights → RGI outline mask → terrain from 2007/2015 DEMs, holes from
   Copernicus → initial thickness → bed = surface − thickness → `ice_domain`.
2. `history.calibrate`: base climate = Kyanjin 1981–2015 climatology (ERA5-Land with each calendar month shifted to
   the Kyanjing AWS 2012–2019 mean, `AWS_MINUS_ERA5LAND`; cooling with height per calendar month as measured
   Kyanjing → Yala Base Camp, `KYANJIN_TO_BASE_CAMP_LAPSE`, assumed to hold above Base Camp too); shift temperature
   so the mean SMB over the
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
- Yala DEMs: `DEM_and_ortho/DEM_and_ortho/` (override `HIMSIM_DATA`), **git-ignored**. 1981 = 10 m, 2007 = 2 m
  (wide valley coverage), 2015 = 1 m; nodata −3.4e38; EPSG:32645. `2015Yala_ortho.tif` is 1.6 GB, never read whole.
- **Vertical datum (inferred):** Yala DEMs are WGS84-ellipsoidal. On rock they sit 30.0–31.5 m below Copernicus,
  matching the EGM2008 undulation −31.4 m. `load_site` converts them. Producer confirmation still pending.
- Copernicus GLO-30: `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N28_00_E085_00_DEM/...`,
  no login; cached as .npy in `data/cache/` (git-ignored). Geoid grid comes via PROJ network (cdn.proj.org).
- Kyanjin (3862 m): gauge precipitation **867 mm/yr** at 3857 m (Immerzeel et al. 2014, cited in Steiner et al. 2021,
  doi:10.1002/hyp.14189); monsoon share 70–90 %. Raw ERA5 gives ~1800 mm, so precipitation is rescaled to 867 over
  1981–2010. Temperature = ERA5-Land adjusted to 3862 m, seasons corrected to the Kyanjing AWS. ICIMOD AWS data (registration needed): Kyanjing
  doi:10.26066/RDS.22464, Yala Base Camp RDS.26859, Yala Glacier RDS.1972507. Yala glaciological mass balance at WGMS.
- ICIMOD AWS downloads (`icimod_aws.STATIONS`), all **git-ignored**, path overrides `HIMSIM_KYANJING_AWS`,
  `HIMSIM_YALA_BC_AWS`, `HIMSIM_YALA_GLACIER_AWS`. The 2016 terms inside the Kyanjing and Base Camp downloads forbid
  copying without ICIMOD consent; all three RDS pages now say CC BY 4.0 (unresolved). Show statistics only, never data.
  Shared layout: hourly, Nepal time, rows label the hour's *end*, `DATE`+`TIME`, NA.
  - Kyanjing 3862 m (28.21081 N 85.56169 E; the station sheet's 85.68619 E is a typo), 2012-03-22 → 2019-12-31;
    timestamps switch format in 2018; 72 months with ≥80 % temperature. PVOL fails: 0 mm through the 2015/2016
    monsoons, ~⅕ of the bucket (BCON) gain in 2018–19, so precipitation only where PVOL and bucket gain agree (33 months).
  - Yala Base Camp 5090 m, rock, 2012-05-08 → 2019; destroyed by the Gorkha earthquake 25 Apr 2015, rebuilt. Faults in
    `bad_periods`: columns reordered (Kyanjing order) from 2019-11-18 19:00; 13 and 17 Jun 2016 TAIR jumps 3→26 °C with
    RH stuck at 100 %; three precipitation windows flagged in the station sheet.
  - Yala Glacier, on the ice, 5291 m from 2016-05-07, moved to 5330 m on 2018-11-28 (`moves`; `z_m` per month).
    Temperature, radiation, wind only (no gauge). doi:10.26066/RDS.1972507.
- Field data for the reality check (in `observations.py`, each with DOI): Sugiyama et al. 2013 (radar 2009: volume
  0.061 km³, upper bound 0.066; centre-line thickness at 5120–5300 m 60/45/31 m in 1982/1996/2009; bed frozen in the
  ablation area) and Stumm et al. 2021 (stakes 2011–2017: −0.80 ± 0.28 m w.e./yr, yearly values, ELA 5380–5518 m,
  gradient 1.04 ± 0.12 m w.e./100 m; area 1.61 km² in 2012). Model centre-line equivalent = 75th percentile of
  thickness in the band.
- Outline: RGI60-15.03954 (2.107 km², Nov 2000). GLIMS WFS layers `GLIMS:RGI_SouthAsiaEast` and
  `GLIMS:RGI2000-v7.0-G-15_south_asia_east_epsg3857` return EPSG:3857, so reproject before saving.

## Reference numbers (regression check after changes; 50 m grid, default settings)
- Melt factors: ice 8.63, snow 5.3 mm w.e. °C⁻¹ d⁻¹ (Shea et al. 2015, Table 2 initial values; their Everest
  calibration 9.7/5.4 gives gradient 0.76 but only 5 matches). Litt et al. 2019 (doi:10.1038/s41598-019-41657-5)
  Table S4 Yala point values are too erratic to use (ice 0–9.0, snow 0–18.5).
- Sunshine rule (`melt_model="eti"`, teacher toggle, **off by default**): TF 2.0 mm w.e. °C⁻¹ d⁻¹ and SRF 0.1 mm w.e.
  W⁻¹ m² d⁻¹ (Litt et al. 2019 Table S4, Yala monsoon 2014 and 2016; chosen before running). Station inputs from the
  Yala Glacier AWS: SW_in 128 (Sep)–307 (Mar) W m⁻², albedo ice 0.23 / snow 0.70 (daily, split at 0.4, Litt's
  threshold); daily-T spread 0.68–3.28 °C (Base Camp) turns monthly means into a share of melting days (normal
  distribution), so melt has no jump at 0 °C. Litt gives no T_ETI value; the model's 0 °C is used. Results vs "ti":
  6/3/2 (gradient 0.56, area 2012 off), tongue −55 vs −44 m, RMSE 7.1 m, shift +0.31 °C, today's climate keeps 10 %.
  Sensitivities: SRF 0.2 (Litt's whole-year 2014/2017 fits) → gradient 0.83, 6/5/0, shift −0.55; on-ice air (T_ETI
  +1.9 °C) → 0.42, 4/4/3; both → 0.69, 7/3/1. Picking SRF after seeing the gradient would be tuning to a check.
- Calibrated station temperature 3.91 °C: the tuning shift on the station-corrected record is **+0.24 °C**
  (+0.05 with one 8 mm factor; +1.41 with a constant 6 °C/km; ERA5-Land climatology +1.42 °C). ELA 5422 m
  (1981–2015) → 5532 m (today).
- Thinning (m/yr), measured vs model: 1981–2007 −0.44 / −0.51; 2007–2015 −0.91 / −0.85; 1981–2015 −0.54 / −0.60.
- 2015 band comparison RMSE ≈ 8.1 m (cell-weighted). Known misfit: the tongue (5100–5200 m) thins too much (−63 vs −44 m).
  The upper glacier is close.
- Area 2.09 km² (1981) → 1.78 (2015) → 1.46 (end 2025). Futures from end-2025: today's climate keeps ~18 % of
  the ice to 2100; +1.5 °C by 2100 → gone ~2084; +2 °C → ~2073; +4 °C → ~2057 (one melt factor: 15 % / 2081 / 2072 /
  2056; constant 6 °C/km: 27 % / 2094 / 2080 / 2060).
- Reality check (standard settings): 7 match, 3 close, 1 off. Matches: thinning 2007–2015, volume 2009 (0.061 vs
  0.061 km³), centre thickness 1982/1996/2009 (60/45/31 vs 59.9/46.6/32.9 m), mean MB 2012–17 (−0.80 vs −0.72), ELA
  (5380–5518 vs 5467). Close: thinning 1981–2007, area 2006/2012 (2.07/1.88 vs 1.82/1.61: outline definition).
  Off: SMB gradient 0.70 vs 1.04 (history: 0.77 raw seasons → 0.87 station seasons, September at 0 °C at the ELA →
  0.62 measured lapse, monsoon 5.1 °C/km → 0.70 snow/ice factors; next suspect: shortwave radiation).
  Stake years: 1 of 6 within error.
- Station checks (model minus measured, °C, year / Jun–Sep / Dec–Feb): Kyanjing +0.18 / +0.26 / −0.14 (72 months);
  Yala Base Camp +0.24 / +0.30 / −0.07 (73 months); Yala Glacier (on ice) +0.93 / +1.23 / +0.58 (40 months). Kyanjing
  and Base Camp both feed the climate (seasons, lapse), so the independent part is the ~0 tuning shift. Measured cooling Kyanjing → Base Camp
  5.7 °C/km (63 months; Jun–Sep ~5.1, Feb–Apr ~6.7–7.0); Base Camp → glacier station −1.9 °C (ice-cooled air).
  Monthly means vs daily means change positive degree-days by only ~0.15 °C equivalent at both Yala stations.
  Kyanjing precipitation in the 33 trusted months: station 1556 mm, model 2096 mm.
If a change moves these, say so explicitly and explain why.

## Testing rules
- Halfar dome + mass-conservation tests guard the flow numerics; `test_ice_domain_*` and
  `test_thickness_ignores_terrain_outside_glacier` guard the domain logic; `test_kyanjin_record_matches_station_facts`
  guards the climate data; `test_equal_melt_factors_give_the_single_factor_model`, `test_snow_melts_slower_than_ice`
  and `test_separate_factors_steepen_the_smb_gradient` guard the snowpack; `test_aws_reader_quality_control`, `test_kyanjing_aws_matches_known_facts`,
  `test_seasonal_correction_constants_match_station_file`, `test_lapse_rate_constants_match_station_files`,
  `test_measured_monthly_lapse_rates`, `test_station_faults_moves_and_lapse_rates`,
  `test_langtang_stations_known_facts`, `test_yala_climate_matches_kyanjing_station` and
  `test_yala_model_monsoon_matches_base_camp` guard the AWS readers, the seasonal correction and the station checks. `test_yala_reality_check` guards the field-data matches; `test_app.py` drives the UI.
Yala tests are skipped when DEMs are absent.
- Add a test for every new physics component or data source.

## Extending
- **New glacier:** `GlacierSite` in `SITES` (bounds ≥1 km beyond the glacier, DEMs, outline GeoJSON in UTM,
  `vertical_datum`). It needs a climate record for its valley too.
- **New ICIMOD station:** an `AwsStation` in `icimod_aws.STATIONS`. Inspect the columns, timestamp formats and the
  station sheet first; list faults in `bad_periods`, moves in `moves`; check PVOL against the bucket gain.
  `validation.station_comparison` compares any station with the model's weather (uses the month's `z_m`).
  After changing station QC, rerun `scripts/kyanjing_offsets.py` and update `AWS_MINUS_ERA5LAND` and
  `KYANJIN_TO_BASE_CAMP_LAPSE`. The teacher lapse slider scales the 12 measured rates to its yearly mean.
- **New field measurement:** a `Measurement` in the site's `measurements` with its DOI; add a model equivalent to
  `validation.MODEL_VALUES` for a new `kind`. Copy uncertainties exactly as the source states them; never invent one.
- **New preset:** `PRESETS` (a `ClimateChange`) with a one-sentence student-friendly `notes`. Describe local warming
  relative to *today*; never label local warming with global targets (e.g. "Paris").
- **Figures:** `viz.py`. `CATEGORICAL` in fixed slot order per scenario (never cycled; the app caps kept runs at 7);
  `INK` for the modelled past and the "today's climate" baseline; 3D views use `glacier_animation` (Play + slider);
  `ICE_RAMP` thickness; `DH_DIVERGING` (red = thinning); neutral greys for terrain; never dual y-axes.

## Licence
Code: AGPL-3.0-or-later (`LICENSE`). Data keep their own licences (see README "Data credits"). Only add
dependencies and data whose terms are compatible, and credit every new data source in the README.

## Working style
- Keep `app/` free of physics and `himsim` free of Streamlit.
- Don't commit or push unless asked. `main` is the published branch (github.com/Binamraaa/HimSim).
