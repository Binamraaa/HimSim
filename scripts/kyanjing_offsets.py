"""Recompute the station constants in himsim/climate/kyanjin.py from the ICIMOD downloads.

    python scripts/kyanjing_offsets.py [path/to/AWSKyangjin.csv]

1. Seasonal temperature correction (Kyanjing AWS minus ERA5-Land, per calendar month):
   ``AWS_MINUS_ERA5LAND`` / ``AWS_OFFSET_YEARS``.
2. Monthly lapse rates Kyanjing -> Yala Base Camp (needs that download too):
   ``KYANJIN_TO_BASE_CAMP_LAPSE`` / ``LAPSE_YEARS``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from himsim.climate.icimod_aws import KYANJING, YALA_BASE_CAMP, lapse_rates, load_aws  # noqa: E402
from himsim.climate.kyanjin import load_kyanjing_aws, load_record, station_temperature_offsets  # noqa: E402

path = Path(sys.argv[1]) if len(sys.argv) > 1 else KYANJING.path
offsets = station_temperature_offsets(load_kyanjing_aws(path), load_record(correct_seasons_to_station=False))
print(offsets.round(2).to_string())
print("AWS_MINUS_ERA5LAND =", tuple(round(float(v), 2) for v in offsets["offset_c"]))
print("AWS_OFFSET_YEARS =", tuple(int(v) for v in offsets["years"]))

if YALA_BASE_CAMP.available():
    lr = lapse_rates(load_kyanjing_aws(path), load_aws(YALA_BASE_CAMP))
    g = lr.groupby(lr.index.month)["lapse_c_per_km"]
    print("KYANJIN_TO_BASE_CAMP_LAPSE =", tuple(round(float(v), 2) for v in g.mean()))
    print("LAPSE_YEARS =", tuple(int(v) for v in g.size()))
