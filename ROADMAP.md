# Roadmap

**Vision:** a free, open simulation platform where students and researchers pick a Himalayan glacier or hazard
site, enter human-readable scenario inputs (temperature change, precipitation, release volume…), and explore
the outcome with the physics explained. Visualisation and learning come first; research-grade accuracy is a
non-goal unless stated.

## Phase 0: Foundation ✅ (Oct 2026)
- Cleaned workspace, archived legacy scripts, git repo.
- `himalsim` package: degree-day SMB, conservative SIA flow (Mahaffy + outflow limiter), adaptive time step.
- Yala site: 1981 surface, RGI 6.0 outline, plasticity-pattern thickness scaled to volume–area scaling.
- Calibration to the 1981→2015 geodetic thinning; hindcast validation (glacier-mean −20.3 m modelled vs −18.5 m observed, band RMSE 6.6 m).
- Streamlit scenario lab with 7 presets, scenario comparison, SMB profile, validation and explainer tabs.

## Phase 1: Make Yala trustworthy and richer
- [ ] Real climate: Kyanjin station records and/or ERA5-Land monthly series instead of the approximate defaults.
- [ ] Separate snow/ice degree-day factors with a simple snowpack (fixes the too-negative upper glacier).
- [ ] Ice thickness from Farinotti et al. (2019) / Millan et al. (2022); compare with the current estimate.
- [ ] Start from the 2007 or 2015 DEM as well, and "future from today" runs.
- [ ] Parameter-uncertainty ensembles (run a scenario 20× with perturbed DDF / thickness / A; show spread).
- [ ] Speed: numba-compile the flux kernel so 25 m runs become interactive.
- [ ] Animated playback and an exportable GIF/MP4 of a run.

## Phase 2: More glaciers of Nepal
- [ ] Generic `GlacierSite.from_rgi(rgi_id)`: outline from the GLIMS WFS (layer `GLIMS:RGI2000-v7.0-G-15_south_asia_east_epsg3857`, proven to work),
      terrain from Copernicus GLO-30, calibration target from Hugonnet et al. (2021) per-glacier geodetic mass balance.
- [ ] Candidate glaciers with field data: Rikha Samba, Mera, Pokalde, AX010, Changri Nup, Lirung, Langtang.
- [ ] Nepal-wide overview with OGGM (flowline model; needs WSL/Linux) as a comparison layer, not a replacement.

## Phase 3: Rasuwa 2026 mass-flow module (`himalsim.massflow`)
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
- [ ] Multi-page app: Glaciers · Mass flows · Learn · About/cite.
- [ ] Save, share and re-load scenarios as small JSON files; a gallery of instructive scenarios.
- [ ] Free hosting (Streamlit Community Cloud or Hugging Face Spaces) with DEMs pre-resampled to model resolution (MB, not GB).
- [ ] Open-source license, citation file, contributor guide, docs site.

## Open questions for the project owner
- Who produced the 1981/2007/2015 Yala DEMs, and may derived (resampled) versions be published?
- License preference for the code (MIT / BSD-3 / GPL)?
- Keep the name "HimalSim"?
