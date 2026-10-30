"""Rebuild himsim/climate/data/kyanjin_monthly.csv from the Open-Meteo archive.

    python scripts/fetch_kyanjin_climate.py [--end 2025-12-31]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from himsim.climate.kyanjin import DATA_FILE, KYANJIN, build_monthly  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--start", default="1960-01-01")
parser.add_argument("--end", default="2025-12-31")
args = parser.parse_args()

frame, metas = build_monthly(args.start, args.end)
header = [
    f"# Monthly climate at {KYANJIN.name}, {KYANJIN.lat} N {KYANJIN.lon} E, adjusted to {KYANJIN.elevation:.0f} m a.s.l.",
    f"# Downloaded {dt.date.today().isoformat()} from the Open-Meteo historical weather API (https://open-meteo.com), licence CC BY 4.0.",
    "# Contains modified Copernicus Climate Change Service information (ERA5: Hersbach et al. 2020; ERA5-Land: Munoz-Sabater et al. 2021).",
    *[f"# {m['model']}: grid cell {m['latitude']:.3f} N {m['longitude']:.3f} E" for m in metas],
    "# t_era5land_c, t_era5_c: monthly mean 2 m air temperature (degC); p_era5_mm: monthly precipitation total (mm), raw ERA5 (not bias-corrected).",
    "# Months with fewer than 25 valid days are empty.",
]
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(DATA_FILE, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(header) + "\n")
    frame.to_csv(f, date_format="%Y-%m-%d")
print(f"wrote {DATA_FILE} ({len(frame)} months)")
