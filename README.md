# HimalSim

An interactive glacier simulator for secondary and high-school students. Explore how Yala Glacier (Langtang,
Nepal) changed since 1981 using real survey data and real weather, then run your own "what if" climate scenarios
to 2100, with the science explained along the way.

**Status:** v0.2. 2D shallow-ice model + monthly degree-day mass balance, driven by the Kyanjin climate record
(1960–2025) and checked against DEMs from 1981, 2007 and 2015. See [ROADMAP.md](ROADMAP.md).

## Quick start (Windows, Anaconda)

```bash
conda activate base                      # has every dependency; or: conda env create -f environment.yml
python -m pytest                         # 33 tests incl. the Halfar benchmark and a check against field data
python -m streamlit run app/streamlit_app.py
```

The DEMs are not in git (≈1.7 GB). Put them in `DEM_and_ortho/DEM_and_ortho/` or point `HIMALSIM_DATA` at their folder.

## Use it from Python

```python
from himalsim.climate.kyanjin import load_record
from himalsim.glacier import ClimateChange, prepare_site, simulate
from himalsim.glacier.history import prepare_history
from himalsim.glacier.validation import reality_check

data = prepare_site("Yala", dx=50)                  # cached on disk after the first call
history = prepare_history(data, load_record())      # calibrate + replay 1981 -> today
print(reality_check(data, history))                 # model vs independent field measurements
scenario = ClimateChange(warming=2.0, precip=-0.1).scenario(history.present_year, 2100)
run = simulate(data.bed, history.present_thickness, 50, history.present_climate, scenario,
               accumulation_mask=data.mask, ice_domain=data.ice_domain)
print(run.volume_remaining_pct, run.year_vanished)
run.to_frame().to_csv("my_scenario.csv")
```

## What's inside

| Path | Contents |
|---|---|
| `himalsim/grid.py` | Model grid, DEM reprojection, gap filling |
| `himalsim/dem.py` | Catalogue of free global DEMs, Copernicus GLO-30 access, ellipsoid ↔ sea-level conversion |
| `himalsim/climate/` | Kyanjin climate record (ERA5-Land / ERA5, bias-corrected to the station), Open-Meteo client |
| `himalsim/glacier/` | scenarios, mass balance, SIA flow, initial thickness, time stepping, sites, history replay, validation |
| `himalsim/viz.py` | Plotly figures |
| `app/` | Streamlit scenario lab + "How it works" explainer |
| `tests/` | Physics tests (mass conservation, Halfar dome, SMB behaviour, Yala hindcast) |
| `legacy/` | The original 2025 scripts, archived |

## Licence

The code is free software under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-or-later).
You may use, study, share and change it. If you share a modified version, or run one as a website, you must
share its source under the same licence. The data listed below keep their own licences.

## Data credits

- Yala DEMs and orthophotos 1981/2007/2015: bias-corrected and co-registered (provenance to be documented).
- Glacier outline: Randolph Glacier Inventory 6.0, RGI60-15.03954 (RGI Consortium 2017), via GLIMS.
- Field measurements: Sugiyama et al. (2013), doi:10.3189/2013AoG64A111 (radar thickness, volume);
  Stumm et al. (2021), doi:10.5194/essd-13-3791-2021 (ICIMOD stake mass balance 2011–2017).
- Climate: ERA5 (Hersbach et al. 2020) and ERA5-Land (Muñoz-Sabater et al. 2021), Copernicus Climate Change Service,
  via Open-Meteo (CC BY 4.0); precipitation scaled to the Kyanjin gauge (Immerzeel et al. 2014; Steiner et al. 2021).
- Copernicus DEM GLO-30: © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018, provided under
  COPERNICUS by the European Union and ESA.

## Acknowledgements

Development was assisted by Claude (Anthropic), an AI assistant used through Claude Code.
