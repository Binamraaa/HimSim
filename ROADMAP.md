# Roadmap

**Vision:** a free, open simulation platform where **secondary and high-school students** (and curious researchers)
pick a Himalayan glacier, enter plain-language scenario inputs (temperature change, precipitation…), and explore
the outcome with the science explained. Learning comes first, and **the data always stays accurate and cited**.

## Phase 0: Foundation ✅ (Oct 2026)
- Cleaned workspace, archived legacy scripts, git repo.
- `himalsim` package: degree-day SMB, conservative SIA flow (Mahaffy + outflow limiter), adaptive time step.
- Yala site: 1981 surface, RGI 6.0 outline, plasticity-pattern thickness scaled to volume–area scaling.
- Calibration to the 1981→2015 geodetic thinning; hindcast validation (glacier-mean −20.3 m modelled vs −18.5 m observed, band RMSE 6.6 m).
- Streamlit scenario lab with 7 presets, scenario comparison, SMB profile, validation and explainer tabs.

## Phase 1: Make Yala trustworthy and richer (in progress, branch `phase1-climate-dem`)
- [x] Kyanjin climate package: ERA5-Land temperature + ERA5 precipitation (1960–2025), precipitation bias-corrected
      to the gauge (867 mm/yr); seasonal cycle from data; loader for ICIMOD station files.
- [x] Replay observed weather 1981→2025; calibrate on real yearly forcing; validate the post-2007 speed-up.
- [x] Future scenarios start from "today" (end of 2025) with the 2016–2025 climate; presets reworded for students.
- [x] Open DEMs: catalogue, Copernicus GLO-30 access, geoid/ellipsoid conversion (Yala DEMs found to be ellipsoidal).
- [x] Physics fixes: ice can't spill over enclosing ridges; thickness estimate ignores terrain beyond the outline.
- [x] Student-friendly app (7 tabs) and explainer.
- [ ] Download the real Kyanjing AWS data from ICIMOD (owner registers) and compare with the reanalysis.
- [x] Reality check against independent field data: radar thickness/volume (Sugiyama 2013) and ICIMOD stake
      mass balance 2011–2017 (Stumm 2021, data in WGMS FoG doi:10.5904/wgms-fog-2021-05). Scorecard in the app.
- [x] Guided, student-first app: 4 steps, two-slider climate input with instant results, Play animations,
      one "ice volume 1981→2100" story chart, keep-and-compare; teacher settings tucked away.
- [x] Speed: SMB lookup table (2× faster runs) and a disk cache, so the app starts in ~1 s after the first build.
- [ ] Steeper mass-balance gradient (model 0.77 vs measured 1.04 m w.e./100 m): try separate snow/ice degree-day
      factors or a simple radiation term, *only* with literature values, and re-run the reality check.
- [ ] Separate snow/ice degree-day factors with a simple snowpack.
- [ ] Ice thickness from Farinotti et al. (2019) / Millan et al. (2022); the tongue over-thinning points here.
- [ ] Parameter-uncertainty ensembles (run a scenario 20× with perturbed DDF / thickness / A; show spread).
- [ ] Speed: numba-compile the flux kernel so 25 m runs become interactive.
- [ ] Exportable GIF/MP4 of a run.

## Phase 2: More glaciers of Nepal
- [ ] Generic `GlacierSite.from_rgi(rgi_id)`: outline from the GLIMS WFS (layer `GLIMS:RGI2000-v7.0-G-15_south_asia_east_epsg3857`, proven to work),
      terrain from Copernicus GLO-30, calibration target from Hugonnet et al. (2021) per-glacier geodetic mass balance.
- [ ] Candidate glaciers with field data: Rikha Samba, Mera, Pokalde, AX010, Changri Nup, Lirung, Langtang.
- [ ] Nepal-wide overview with OGGM (flowline model; needs WSL/Linux) as a comparison layer, not a replacement.

## Phase 3: Rasuwa 2026 mass-flow module (`himalsim.massflow`), a separate case study, parked
The 26 Aug 2026 Bhote Koshi event began as a rock-ice collapse at ~5,200 m near the Nepal–Tibet border and
became a debris flood that reached Rasuwagadhi in ~7.5 minutes. That is a **mass-flow** problem, not glacier flow.
- [ ] Physics: depth-averaged shallow flow over terrain with **Voellmy friction** (Coulomb μ + turbulent ξ), the
      approach used by RAMMS. Optional entrainment of bed material (volume growth downstream).
- [ ] Numerics: finite-volume shallow-water solver (HLL flux, hydrostatic reconstruction for wet/dry fronts), numba.
- [ ] Data: Copernicus GLO-30 DEM for the Bhote Koshi / Trishuli corridor; event source area from published analyses.
- [ ] Scenario inputs: release volume and location, μ, ξ, entrainment rate, tributary inflow.
- [ ] Outputs: maximum depth / velocity / arrival-time maps, runout, flow hydrograph at Rasuwagadhi and downstream bridges.
- [ ] Validation targets: travel time to Rasuwagadhi (~7.5 min), ~21 km in the first 7 min, mapped inundation (USGS / ICIMOD products).
- [ ] Benchmark against r.avaflow on the same input.

## Phase 4: The platform
- [ ] Classroom features: guided activities/worksheets per tab, a glossary, Nepali-language UI.
- [ ] Multi-page app: Glaciers · Mass flows · Learn · About/cite.
- [ ] Save, share and re-load scenarios as small JSON files; a gallery of instructive scenarios.
- [ ] Free hosting (Streamlit Community Cloud or Hugging Face Spaces) with DEMs pre-resampled to model resolution (MB, not GB).
- [x] Licence: AGPL-3.0-or-later (Oct 2026).
- [ ] Citation file, contributor guide, docs site.

## Open questions for the project owner
- Who produced the 1981/2007/2015 Yala DEMs, and may derived (resampled) versions be published?
- Keep the name "HimalSim"?
