"""Download one glacier outline from the Randolph Glacier Inventory 6.0 (via GLIMS) and save it in UTM.

    python scripts/fetch_rgi_outline.py RGI60-15.04847 rikha_samba_rgi60 EPSG:32644

Writes ``himsim/glacier/outlines/<name>.geojson``: the polygon in the model's UTM zone plus the RGI facts (area,
elevation range, outline date). The GLIMS WFS serves EPSG:3857 (Web Mercator), whose areas are inflated by
1/cos²(latitude), so the outline is reprojected and its area checked against the RGI value. Needs internet.
RGI 6.0: RGI Consortium (2017), doi:10.7265/N5-RGI-60.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Transformer

WFS = "https://www.glims.org/geoserver/GLIMS/ows"
LAYER = "GLIMS:RGI_SouthAsiaEast"  # RGI region 15 (South Asia East); other regions use other layers
OUT_DIR = Path(__file__).resolve().parents[1] / "himsim" / "glacier" / "outlines"


def fetch(rgi_id: str) -> dict:
    query = urllib.parse.urlencode({
        "service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": LAYER,
        "outputFormat": "application/json", "CQL_FILTER": f"RGIID='{rgi_id}'"})
    with urllib.request.urlopen(f"{WFS}?{query}", timeout=120) as r:
        data = json.load(r)
    if len(data.get("features", [])) != 1:
        raise SystemExit(f"Expected one outline for {rgi_id}, got {len(data.get('features', []))}")
    return data


def polygon_area(ring: list[list[float]]) -> float:
    return 0.5 * abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rgi_id")
    parser.add_argument("name", help="output file name without extension")
    parser.add_argument("crs", help="model CRS, e.g. EPSG:32644 (UTM 44N) or EPSG:32645 (UTM 45N)")
    args = parser.parse_args()

    data = fetch(args.rgi_id)
    src_crs = data["crs"]["properties"]["name"].split("::")[-1]
    tr = Transformer.from_crs(f"EPSG:{src_crs}", args.crs, always_xy=True)
    feature = data["features"][0]
    p = feature["properties"]
    geom = feature["geometry"]
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    utm = [[[[round(v, 2) for v in tr.transform(x, y)] for x, y in ring] for ring in poly] for poly in polys]
    area = sum(polygon_area(poly[0]) - sum(polygon_area(h) for h in poly[1:]) for poly in utm) / 1e6
    if abs(area - p["AREA"]) > 0.02 * p["AREA"]:
        raise SystemExit(f"Reprojected area {area:.3f} km² differs from RGI {p['AREA']} km²: check the CRS")

    out = {
        "type": "FeatureCollection",
        "name": args.name,
        "crs": {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{args.crs.split(':')[-1]}"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "rgi_id": p["RGIID"], "glacier_name": p.get("NAME") or "", "area_km2": p["AREA"],
                "zmin": p["ZMIN"], "zmax": p["ZMAX"], "zmed": p["ZMED"], "outline_date": p["BGNDATE"],
                "source": f"Randolph Glacier Inventory 6.0 (RGI Consortium 2017), via GLIMS WFS layer {LAYER}",
            },
            "geometry": {"type": "MultiPolygon", "coordinates": utm},
        }],
    }
    path = OUT_DIR / f"{args.name}.geojson"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
    print(f"Wrote {path}: {p['RGIID']} {p.get('NAME') or ''}, {area:.3f} km² in {args.crs} (RGI {p['AREA']} km²), "
          f"{p['ZMIN']}–{p['ZMAX']} m, outline {p['BGNDATE']}")


if __name__ == "__main__":
    main()
