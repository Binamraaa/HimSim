"""Open elevation data: a catalogue of free global DEMs, Copernicus GLO-30 access, and vertical datums.

Two different "zero heights" are used for elevations:
  * the WGS84 *ellipsoid*, a smooth mathematical shape. GPS and many satellite/drone DEMs use it.
  * the *geoid* (here EGM2008), roughly mean sea level. Maps, weather stations and Copernicus use it.
In Langtang the geoid lies ~31 m below the ellipsoid, so the same rock is "31 m higher" in an
ellipsoidal DEM. Mixing the two silently shifts every elevation.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyproj import Transformer
from rasterio.warp import Resampling

from himsim.grid import Grid, read_on_grid

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "data" / "cache"  # git-ignored


@dataclass(frozen=True)
class OpenDem:
    name: str
    resolution: str
    epoch: str
    method: str
    vertical_datum: str
    access: str
    licence: str
    glacier_notes: str


OPEN_DEMS: tuple[OpenDem, ...] = (
    OpenDem("Copernicus GLO-30", "30 m (1″)", "2011–2015", "TanDEM-X radar (X-band)", "EGM2008 geoid",
            "AWS open bucket, no login (used by HimSim)", "Copernicus DEM licence: free, attribution required",
            "Best open global DEM in steep terrain. Radar penetrates a little into dry snow/firn."),
    OpenDem("FABDEM", "30 m", "2011–2015", "Copernicus GLO-30 with forests & buildings removed", "EGM2008 geoid",
            "University of Bristol download", "CC BY-NC-SA 4.0 (non-commercial)",
            "Bare-earth version of GLO-30. Same as GLO-30 above the tree line; useful for valley floods."),
    OpenDem("NASADEM / SRTM GL1", "30 m (1″)", "Feb 2000", "SRTM radar (C-band)", "EGM96 geoid",
            "NASA Earthdata or OpenTopography (free account)", "Public domain",
            "A year-2000 snapshot, so useful for glacier change. C-band penetrates snow/firn several metres; voids on steep slopes."),
    OpenDem("ALOS World 3D (AW3D30)", "30 m (1″)", "2006–2011", "PRISM optical stereo", "EGM96 geoid",
            "JAXA (free registration)", "Free with attribution",
            "Optical, so no radar penetration, but clouds and snow contrast cause voids/noise."),
    OpenDem("ASTER GDEM v3", "30 m (1″)", "2000–2013 stack", "ASTER optical stereo", "EGM96 geoid",
            "NASA Earthdata (free account)", "Free with attribution",
            "Noisy, with artefacts in steep and snowy terrain; mostly superseded."),
    OpenDem("HMA 8 m DEMs (Shean et al.)", "8 m", "2002–2016 strips", "WorldView/GeoEye stereo", "WGS84 ellipsoid",
            "NSIDC (NASA Earthdata account)", "Free with attribution",
            "High-resolution, multi-date strips over High Mountain Asia; excellent for glacier change, patchy coverage."),
)


def copernicus_tile_url(lat_floor: int, lon_floor: int) -> str:
    ns = f"N{lat_floor:02d}" if lat_floor >= 0 else f"S{-lat_floor:02d}"
    ew = f"E{lon_floor:03d}" if lon_floor >= 0 else f"W{-lon_floor:03d}"
    name = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
    return f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"


def _grid_lonlat(grid: Grid) -> tuple[np.ndarray, np.ndarray]:
    xx, yy = np.meshgrid(grid.x, grid.y)
    lon, lat = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform(xx, yy)
    return lon, lat


def read_copernicus(grid: Grid, use_cache: bool = True) -> np.ndarray:
    """Copernicus GLO-30 heights (m above the EGM2008 geoid) on ``grid``. Needs internet the first time."""
    cache = CACHE_DIR / f"cop30_{grid.crs.replace(':', '')}_{grid.xmin:.0f}_{grid.ymax:.0f}_{grid.dx:g}_{grid.nx}x{grid.ny}.npy"
    if use_cache and cache.exists():
        return np.load(cache)
    lon, lat = _grid_lonlat(grid)
    out = np.full(grid.shape, np.nan)
    for la in range(math.floor(lat.min()), math.floor(lat.max()) + 1):
        for lo in range(math.floor(lon.min()), math.floor(lon.max()) + 1):
            tile = read_on_grid(copernicus_tile_url(la, lo), grid, Resampling.bilinear)
            out = np.where(np.isfinite(out), out, tile)
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(cache, out)
    return out


def geoid_undulation(grid: Grid, fallback: float | None = None) -> np.ndarray:
    """EGM2008 geoid height N above the WGS84 ellipsoid (m) at every grid cell.

    Uses the PROJ geoid grid (downloaded once from cdn.proj.org and cached by PROJ).
    If the grid isn't available, PROJ silently returns 0, so we check for that and use
    ``fallback`` (with a warning) instead of returning a wrong answer.
    """
    import pyproj

    pyproj.network.set_network_enabled(True)
    lon, lat = _grid_lonlat(grid)
    _, _, h_ortho = Transformer.from_crs("EPSG:4979", "EPSG:4326+3855", always_xy=True).transform(
        lon, lat, np.zeros_like(lon))
    n = -np.asarray(h_ortho)
    if not np.isfinite(n).all() or np.abs(n).max() < 0.5:
        if fallback is None:
            raise RuntimeError("EGM2008 geoid grid unavailable (PROJ network blocked?) and no fallback given")
        warnings.warn(f"EGM2008 geoid grid unavailable; using constant undulation {fallback} m", stacklevel=2)
        return np.full(grid.shape, float(fallback))
    return n


def ellipsoid_to_orthometric(heights: np.ndarray, grid: Grid, fallback: float | None = None) -> np.ndarray:
    """Convert WGS84 ellipsoidal heights to heights above the EGM2008 geoid (≈ above sea level)."""
    return heights - geoid_undulation(grid, fallback)
