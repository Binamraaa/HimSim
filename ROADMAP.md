# Roadmap

**Vision:** a free, open simulation platform where **secondary and high-school students** (and curious researchers)
pick a Himalayan glacier, enter plain-language scenario inputs (temperature change, precipitation…), and explore
the outcome with the science explained. Learning comes first, and **the data always stays accurate and cited**.

## Phase 0: Foundation ✅ (Oct 2026)
- Cleaned workspace, archived legacy scripts, git repo.
- `himsim` package: degree-day SMB, conservative SIA flow (Mahaffy + outflow limiter), adaptive time step.
- Yala site: 1981 surface, RGI 6.0 outline, plasticity-pattern thickness scaled to volume–area scaling.
- Calibration to the 1981→2015 geodetic thinning; hindcast validation (glacier-mean −20.3 m modelled vs −18.5 m observed, band RMSE 6.6 m).
- Streamlit scenario lab with 7 presets, scenario comparison, SMB profile, validation and explainer tabs.

## Phase 1: Make Yala trustworthy and richer (in progress, on `main`)
- [x] Kyanjin climate package: ERA5-Land temperature + ERA5 precipitation (1960–2025), precipitation bias-corrected
      to the gauge (867 mm/yr); seasonal cycle from data; loader for ICIMOD station files.
- [x] Replay observed weather 1981→2025; calibrate on real yearly forcing; validate the post-2007 speed-up.
- [x] Future scenarios start from "today" (end of 2025) with the 2016–2025 climate; presets reworded for students.
- [x] Open DEMs: catalogue, Copernicus GLO-30 access, geoid/ellipsoid conversion (Yala DEMs found to be ellipsoidal).
- [x] Physics fixes: ice can't spill over enclosing ridges; thickness estimate ignores terrain beyond the outline.
- [x] Student-friendly app (7 tabs) and explainer.
- [x] Kyanjing AWS (ICIMOD, hourly 2012–2019) read, quality-controlled and compared with the model's weather in the
      app (tab 3). Tuned temperature matches the station's mean (+0.01 °C over 72 months; raw ERA5-Land −1.1 °C), but
      the seasonal cycle is too strong (+1.4 °C monsoon, −1.4 °C winter). The gauge's PVOL is unreliable for long
      stretches (0 mm in the 2015/2016 monsoons, ~⅕ of the bucket gain in 2018–19); 33 trusted months.
- [x] Seasonal temperature cycle corrected to the Kyanjing AWS (12 per-calendar-month offsets, ERA5-Land winters
      2–3 °C too cold). Recalibrated: tuning shift +1.41 °C; SMB gradient 0.77 → 0.87 (off → close); reality check
      6/5/0; futures nearly unchanged.
- [ ] Ask ICIMOD whether derived monthly AWS values may be published with the app (download terms vs. CC BY 4.0 page).
- [x] Yala Base Camp (RDS.26859) and Yala Glacier (RDS.1972507) AWS read and compared (app tab 3). Kyanjin → Base Camp
      cools 5.7 °C/km (monsoon ~5.1); the tuned model's monsoon at Base Camp is +0.4 °C, so the +1.4 °C tuning mostly
      stands in for the gentler monsoon lapse rate. Air over the ice is ~1.9 °C colder than at Base Camp.
- [x] Measured monthly lapse rates (Kyanjin → Base Camp, 4.9–7.0 °C/km) replace the constant 6 °C/km. The tuning
      shift fell to +0.05 °C (model matches both off-glacier stations); reality check 7/3/1; 2007–2015 thinning now
      matches. SMB gradient back to "off" (0.62). Futures more pessimistic (today's climate keeps ~15 % by 2100;
      +2 °C → gone ~2072).
- [x] Reality check against independent field data: radar thickness/volume (Sugiyama 2013) and ICIMOD stake
      mass balance 2011–2017 (Stumm 2021, data in WGMS FoG doi:10.5904/wgms-fog-2021-05). Scorecard in the app.
- [x] Guided, student-first app: 4 steps, two-slider climate input with instant results, Play animations,
      one "ice volume 1981→2100" story chart, keep-and-compare; teacher settings tucked away.
- [x] Speed: SMB lookup table (2× faster runs) and a disk cache, so the app starts in ~1 s after the first build.
- [x] Separate snow/ice degree-day factors (5.3 / 8.63 mm w.e. °C⁻¹ d⁻¹, Shea et al. 2015) with a monthly
      snowpack (balance year from 1 Oct). SMB gradient 0.62 → 0.70; reality check unchanged (7/3/1); tuning +0.24 °C.
- [x] Sunshine term (enhanced temperature index) with Yala Glacier AWS radiation and albedo and Litt et al. (2019)
      Yala factors, as a teacher option. With the monsoon factors it flattens the SMB gradient (0.56) though it improves
      the tongue; with SRF 0.2 it gives 0.83. Owner decision (31 Oct 2026): degree days stay the default; the
      sunshine rule remains a teacher option, and SRF is not to be picked after seeing the reality check.
- [x] Snow ageing in the sunshine rule: fresh-snow albedo 0.79 decaying to 0.64 in 2.8 days, fitted at the Yala
      Glacier AWS, with the Base Camp wet-day frequency. Sunshine-rule gradient 0.56 → 0.59, reality check 6/3/2 → 7/2/2;
      default ("ti") unchanged. Snow albedo is not the main cause of the gradient gap (all variants 0.59–0.61).
- [ ] SMB gradient still 0.70 vs 1.04. Candidates: albedo of bare ice varying with height;
      topographic shading and aspect; on-ice air temperature (glacier cooling) in the melt rule.
- [ ] Ice thickness from Farinotti et al. (2019) / Millan et al. (2022); the tongue over-thinning points here.
- [ ] Parameter-uncertainty ensembles (run a scenario 20× with perturbed DDF / thickness / A; show spread).
- [ ] Speed: numba-compile the flux kernel so 25 m runs become interactive.
- [ ] Exportable GIF/MP4 of a run.

## Phase 2: More glaciers of Nepal
- [ ] Generic `GlacierSite.from_rgi(rgi_id)`: outline from the GLIMS WFS (layer `GLIMS:RGI2000-v7.0-G-15_south_asia_east_epsg3857`, proven to work),
      terrain from Copernicus GLO-30, calibration target from Hugonnet et al. (2021) per-glacier geodetic mass balance.
      If the GLIMS WFS is down (502 on 2 Nov 2026), OGGM mirrors RGI 6.2 (`cluster.klima.uni-bremen.de/~oggm/rgi/`)
      and the Hugonnet per-glacier rates (`.../~oggm/geodetic_ref_mb/`).
- [ ] Candidate glaciers with field data: Rikha Samba, Mera, Pokalde, AX010, Changri Nup, Lirung, Langtang.
      Debris-covered (Lirung, Langtang) and lake-calving glaciers need new physics; clean-ice benchmark glaciers first.
      Feasibility check (2 Nov 2026):
  - **Rikha Samba (next):** one named RGI polygon, RGI60-15.04847 (6.504 km², 5380–6513 m, Sept 2001), a single
    south-flowing valley glacier (2603 cells at 50 m), UTM 44N. Hugonnet 2000–2020: −0.44 ± 0.14 m w.e./yr (91 % of
    the area measured). Field data, all ICIMOD: stake mass balance since 2011 (WGMS; Stumm et al. ESSD), raw GPR 2015
    (doi:10.26066/RDS.36030, CC BY 4.0), AWS (doi:10.26066/RDS.26858, CC BY 4.0; period, elevation and variables not on
    the page). Still to settle: a precipitation reference for the Mustang rain shadow; no historical survey DEMs, so
    the start surface is Copernicus (~2011–2015) with a 2001 outline.
  - **Mera:** not one RGI polygon. The massif is split into 03582/03583/03584/03586/03590–03595 (03583 reaches
    4933–6312 m, close to the published 4940–6420 m). The outline must be taken from Wagnon et al. (2021) before any
    run (Cambridge and IRD were both offline on 2 Nov 2026). Hugonnet 2000–2020 for those pieces: −0.20 to −0.37 m
    w.e./yr. Climate: GLACIOCLIM database; Zenodo 14015618 (Mera/Khare stations 2019–2022, licence unchecked). The
    ESSD 2026 Everest AWS set (doi:10.5194/essd-18-7253-2026) has no Mera station.
- [ ] Nepal-wide overview with OGGM (flowline model; needs WSL/Linux) as a comparison layer, not a replacement.

## Phase 3: Rasuwa 2026 mass-flow module (`himsim.massflow`), a separate case study, parked
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
- [x] In-app guide on the website (Nov 2026): hover tips on every section ("what you see / how to read it / what it
      means"), a 5-card welcome tour on the first visit, and 12 "Try this" missions (tipping point, committed loss,
      snow vs warming, gradual vs sudden, the snowline, the reality check) that complete from what students do.
- [ ] Classroom features: printable worksheets with a teacher answer sheet, a glossary, Nepali-language UI.
- [x] Student website (Nov 2026): `python -m web`, FastAPI + plain HTML/JS, "clean glacier" design; the Streamlit
      app stays as the teacher lab. Next: teacher settings and the DEM explainer on the website, Nepali UI.
- [ ] Multi-page app: Glaciers · Mass flows · Learn · About/cite.
- [ ] Save, share and re-load scenarios as small JSON files; a gallery of instructive scenarios.
- [ ] Free hosting on Hugging Face Spaces (owner's choice, 3 Nov 2026). Ready: `scripts/build_space.py` builds a 1 MB
      Space (Docker) from a deploy bundle (`web/bundle.py`: 50 m grids + station statistics); tested locally without
      DEMs or station files, identical answers. Still to do: create the Space and upload; later a custom domain.
- [x] Licence: AGPL-3.0-or-later (Oct 2026).
- [ ] Citation file, contributor guide, docs site.

## Open questions for the project owner
- Who produced the 1981/2007/2015 Yala DEMs? (Publishing derived 50 m versions: allowed, owner, 3 Nov 2026; the
  producer still needs crediting in the README.)
