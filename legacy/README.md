# Legacy scripts (April–May 2025)

The first attempts at the Yala model, kept for reference. **Do not edit or import these.** Everything useful
has been rebuilt in the `himalsim` package. They hard-code `C:/Users/ALiEN/...` paths.

| File | What it was | Why it was superseded |
|---|---|---|
| `ICE_SHEET_DEM.py` | Streamlit, phase 1: load the 1981 DEM and plot it in 3D | Loader now lives in `himalsim/grid.py` |
| `ICE_SHEET_DEM_P2.py` | Phase 2: SIA flow + SMB functions, no time loop | Flux constant ~10⁹× too small and missing the slope term; divergence via `np.gradient` (not conservative) |
| `ICE_SHEET_DEM_P3.py` | Phase 3: SIA with forward-Euler animation loop | Same flux problems; SMB froze everything (freezing level at ~770 m a.s.l.) |
| `FINAL_MODEL.py` | Replaced SIA with ∇²H diffusion + RK4 | Diffusing *thickness* ignores slope, so ice doesn't flow downhill |
| `DASH_MODEL.py` | Same physics in Plotly Dash | Doesn't run: undefined `reset_counter`, invalid `outputs_list[...]['disabled']` lookups |

Shared problem: the 1981 **ice surface** was used as the **bed**, so the model grew a new glacier on top of the old one.

`screenshots/` holds debugging captures from that period.
