# HimalSim

A learning-oriented simulation toolkit for Himalayan glaciers (and, next, mass flows such as the 2026 Rasuwa
debris flood). Pick a glacier, describe a climate scenario in plain terms (warming rate, precipitation change), and
watch what the glacier does, with the physics explained along the way.

**Status:** v0.1. Yala Glacier (Langtang, Nepal) 2D shallow-ice model with a degree-day mass balance, validated
against DEMs from 1981, 2007 and 2015. See [ROADMAP.md](ROADMAP.md) for where it's going.

## Quick start (Windows, Anaconda)

```bash
conda activate base                      # has every dependency; or: conda env create -f environment.yml
python -m pytest                         # 18 tests incl. the Halfar analytical benchmark
python -m streamlit run app/streamlit_app.py
```

The DEMs are not in git (≈1.7 GB). Put them in `DEM_and_ortho/DEM_and_ortho/` or point `HIMALSIM_DATA` at their folder.

## Use it from Python

```python
from himalsim.glacier import SITES, load_site, simulate, Scenario
from himalsim.glacier.validation import calibrated_climate

data = load_site(SITES["Yala"], dx=50)
climate, observed_rate = calibrated_climate(data)
run = simulate(data.bed, data.thickness, 50, climate,
               Scenario("My scenario", years=100, temp_trend=0.3, precip_change=0.1),
               accumulation_mask=data.mask)
print(run.volume_remaining_pct, run.year_vanished)
run.to_frame().to_csv("my_scenario.csv")
```

## What's inside

| Path | Contents |
|---|---|
| `himalsim/grid.py` | Model grid, DEM reprojection, gap filling |
| `himalsim/glacier/` | climate & scenarios, mass balance, SIA flow, initial thickness, time stepping, sites, validation |
| `himalsim/viz.py` | Plotly figures |
| `app/` | Streamlit scenario lab + "How it works" explainer |
| `tests/` | Physics tests (mass conservation, Halfar dome, SMB behaviour, Yala hindcast) |
| `legacy/` | The original 2025 scripts, archived |

## Data credits

- Yala DEMs and orthophotos 1981/2007/2015: bias-corrected and co-registered (provenance to be documented).
- Glacier outline: Randolph Glacier Inventory 6.0, RGI60-15.03954 (RGI Consortium 2017), via GLIMS.
