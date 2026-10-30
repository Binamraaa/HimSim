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
from scipy.ndimage import label

from himalsim.dem import geoid_undulation, read_copernicus
from himalsim.grid import Grid, coverage_on_grid, fill_gaps, read_on_grid
from himalsim.store import cached
from himalsim.glacier.observations import YALA_MEASUREMENTS, YALA_YEARLY_MASS_BALANCE, Measurement
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
    vertical_datum: str = "geoid"  # "geoid" (heights above sea level) or "ellipsoid" (converted on load)
    geoid_fallback: float | None = None  # EGM2008 undulation (m) to use if the PROJ geoid grid is unavailable
    measurements: tuple[Measurement, ...] = ()  # independent field data for the reality check
    yearly_mass_balance: tuple[tuple[int, tuple[float, float]], ...] = ()  # (year, (m w.e., ±)) from stakes

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
    # Inferred, not documented by the DEM producer: on ice-free terrain all three DEMs sit 30.0-31.5 m
    # below Copernicus GLO-30 (EGM2008 heights), matching the EGM2008 undulation here (-31.4 m).
    vertical_datum="ellipsoid",
    geoid_fallback=-31.4,
    measurements=YALA_MEASUREMENTS,
    yearly_mass_balance=tuple(YALA_YEARLY_MASS_BALANCE.items()),
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
    ice_domain: np.ndarray  # where ice may exist: the glacier plus the connected valley below its snout
    observed: dict[int, np.ndarray]  # observed surfaces by year, m above the EGM2008 geoid (NaN outside coverage)
    notes: list[str]  # how the domain was built, for display


ADVANCE_MARGIN_M = 50.0  # ice may advance onto connected terrain up to this far above the initial snout


def ice_domain_mask(surface: np.ndarray, mask: np.ndarray, margin: float = ADVANCE_MARGIN_M) -> np.ndarray:
    """The glacier plus the terrain it could advance onto: lower than its snout (+margin) and connected to it.

    This keeps the model glacier inside its own basin. Without it, ice at the top of the
    glacier spills over the surrounding ridge crests into neighbouring valleys.
    """
    snout = surface[mask].min()
    candidate = mask | (surface < snout + margin)
    labels, _ = label(candidate)
    return np.isin(labels, np.unique(labels[mask]))


def _outline_mask(site: GlacierSite, grid: Grid) -> np.ndarray:
    with open(site.outline_geojson) as f:
        gj = json.load(f)
    geoms = [feat["geometry"] for feat in gj["features"]] if gj.get("type") == "FeatureCollection" else [gj]
    return rasterize(geoms, out_shape=grid.shape, transform=grid.transform, fill=0, default_value=1).astype(bool)


def load_site(site: GlacierSite, dx: float = 50.0, thickness_method: str = "scaled",
              use_copernicus: bool = True) -> SiteData:
    """Build the model domain: glacier mask, surface, ice thickness and bed.

    All heights are converted to metres above the EGM2008 geoid (≈ sea level), the datum
    of weather stations and Copernicus. The off-glacier terrain comes from the
    ``terrain_years`` DEMs, which are assumed stable outside the glacier. Remaining holes
    are filled from Copernicus GLO-30 (or interpolated when offline). The glacier mask is
    the outline if given, otherwise the ``start_year`` DEM footprint.
    Bed = surface - estimated thickness.
    """
    grid = site.grid(dx)
    notes = []
    observed = {year: read_on_grid(site.path(year), grid) for year in site.dems}
    if site.vertical_datum == "ellipsoid":
        n = geoid_undulation(grid, site.geoid_fallback)
        observed = {year: z - n for year, z in observed.items()}
        notes.append(f"Site DEMs converted from WGS84 ellipsoid to EGM2008 heights (geoid {n.mean():+.1f} m).")

    if site.outline_geojson:
        mask = _outline_mask(site, grid)
        notes.append(f"Glacier outline: {Path(site.outline_geojson).stem}.")
    else:
        mask = coverage_on_grid(site.path(site.start_year), grid) >= 0.5
        notes.append(f"Glacier outline: footprint of the {site.start_year} DEM.")
    mask &= np.isfinite(observed[site.start_year])

    terrain = np.full(grid.shape, np.nan)
    for year in site.terrain_years:
        terrain = np.where(np.isfinite(terrain), terrain, observed[year])
    holes = ~np.isfinite(terrain)
    if holes.any() and use_copernicus:
        try:
            terrain = np.where(holes, read_copernicus(grid), terrain)
            notes.append(f"{holes.mean():.0%} of the terrain filled from Copernicus GLO-30.")
        except Exception as exc:  # offline: fall back to interpolation
            notes.append(f"Copernicus unavailable ({type(exc).__name__}); terrain gaps interpolated.")
    terrain = fill_gaps(terrain)

    surface = np.where(mask, observed[site.start_year], terrain)
    thickness = initial_thickness(surface, mask, dx, thickness_method)
    return SiteData(site=site, grid=grid, surface=surface, bed=surface - thickness, thickness=thickness,
                    mask=mask, ice_domain=ice_domain_mask(surface, mask), observed=observed, notes=notes)


def prepare_site(name: str, dx: float = 50.0) -> SiteData:
    """``load_site`` with a disk cache: the raw DEMs are only read the first time.

    The cache is keyed on the code, not on the DEM files: delete ``data/cache`` after replacing DEMs.
    """
    return cached("site", (name, float(dx)), lambda: load_site(SITES[name], dx=dx))
