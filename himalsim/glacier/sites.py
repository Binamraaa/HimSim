"""Glacier sites: where the data lives and how to turn it into a model domain.

Adding a new glacier = adding a ``GlacierSite`` entry to ``SITES``.

Data root defaults to ``<repo>/DEM_and_ortho/DEM_and_ortho`` and can be
overridden with the ``HIMALSIM_DATA`` environment variable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rasterio.features import rasterize

from himalsim.grid import Grid, coverage_on_grid, fill_gaps, read_on_grid
from himalsim.glacier.thickness import initial_thickness

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("HIMALSIM_DATA", REPO_ROOT / "DEM_and_ortho" / "DEM_and_ortho"))
OUTLINE_DIR = Path(__file__).resolve().parent / "outlines"  # small GeoJSONs, versioned with the code


@dataclass(frozen=True)
class GlacierSite:
    name: str
    description: str
    bounds: tuple[float, float, float, float]  # xmin, ymin, xmax, ymax in ``crs``
    dems: dict[int, str]  # year -> DEM filename in DATA_ROOT
    start_year: int  # the DEM whose surface is the initial ice surface
    terrain_years: tuple[int, ...]  # DEMs (in priority order) used for ice-free terrain around the glacier
    crs: str = "EPSG:32645"
    outline_geojson: str | None = None  # glacier outline (Polygon in ``crs``); falls back to the start DEM footprint

    def path(self, year: int) -> Path:
        return DATA_ROOT / self.dems[year]

    def grid(self, dx: float) -> Grid:
        return Grid.from_bounds(*self.bounds, dx=dx, crs=self.crs)


YALA = GlacierSite(
    name="Yala",
    description="Yala Glacier, Langtang valley, Rasuwa district (~28.23 N, 85.62 E). ICIMOD benchmark glacier.",
    bounds=(361500.0, 3121500.0, 366500.0, 3126500.0),
    dems={
        1981: "1981Yala_dem_20_-10_bias_cor.tif",
        2007: "2007Yala_dem_0_-4_bias_cor.tif",
        2015: "2015Yala_dem_0_0_bias_cor.tif",
    },
    start_year=1981,
    terrain_years=(2007, 2015),
    # RGI60-15.03954, outline from Nov 2000 (2.107 km2). The 1981 DEM footprint is ~4.1 km2
    # because it also covers a neighbouring glacier and stable ground below the terminus.
    outline_geojson=str(OUTLINE_DIR / "yala_rgi60.geojson"),
)

SITES: dict[str, GlacierSite] = {YALA.name: YALA}


@dataclass
class SiteData:
    site: GlacierSite
    grid: Grid
    surface: np.ndarray  # initial surface (ice where glaciated, terrain elsewhere)
    bed: np.ndarray
    thickness: np.ndarray  # initial ice thickness
    mask: np.ndarray  # initial glacier extent
    observed: dict[int, np.ndarray]  # observed surfaces by year (NaN outside each DEM's coverage)


def _outline_mask(site: GlacierSite, grid: Grid) -> np.ndarray:
    with open(site.outline_geojson) as f:
        gj = json.load(f)
    geoms = [feat["geometry"] for feat in gj["features"]] if gj.get("type") == "FeatureCollection" else [gj]
    return rasterize(geoms, out_shape=grid.shape, transform=grid.transform, fill=0, default_value=1).astype(bool)


def load_site(site: GlacierSite, dx: float = 50.0, thickness_method: str = "scaled") -> SiteData:
    """Build the model domain: glacier mask, surface, ice thickness and bed.

    The off-glacier terrain comes from the ``terrain_years`` DEMs, which are assumed
    stable outside the glacier. The glacier mask is the outline if given, otherwise
    the ``start_year`` DEM footprint. Bed = surface - estimated thickness.
    """
    grid = site.grid(dx)
    observed = {year: read_on_grid(site.path(year), grid) for year in site.dems}

    if site.outline_geojson:
        mask = _outline_mask(site, grid)
    else:
        mask = coverage_on_grid(site.path(site.start_year), grid) >= 0.5
    mask &= np.isfinite(observed[site.start_year])

    terrain = np.full(grid.shape, np.nan)
    for year in site.terrain_years:
        terrain = np.where(np.isfinite(terrain), terrain, observed[year])
    terrain = fill_gaps(terrain)

    surface = np.where(mask, observed[site.start_year], terrain)
    thickness = initial_thickness(surface, mask, dx, thickness_method)
    return SiteData(site=site, grid=grid, surface=surface, bed=surface - thickness,
                    thickness=thickness, mask=mask, observed=observed)
