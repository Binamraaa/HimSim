"""Model grid definition and raster I/O.

Every array in the model lives on a ``Grid``: a north-up raster in a projected CRS.
Row 0 is the northern edge, so the row index increases southward. The physics only
uses index-space differences, so this orientation never needs special handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.fill import fillnodata
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject


@dataclass(frozen=True)
class Grid:
    """A north-up regular grid. ``(xmin, ymax)`` is the top-left corner of the top-left cell."""

    xmin: float
    ymax: float
    dx: float
    nx: int
    ny: int
    crs: str = "EPSG:32645"  # UTM 45N covers central Nepal

    @classmethod
    def from_bounds(cls, xmin: float, ymin: float, xmax: float, ymax: float, dx: float, crs: str = "EPSG:32645") -> Grid:
        nx = int(round((xmax - xmin) / dx))
        ny = int(round((ymax - ymin) / dx))
        return cls(xmin=xmin, ymax=ymax, dx=dx, nx=nx, ny=ny, crs=crs)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.ny, self.nx)

    @property
    def transform(self) -> Affine:
        return from_origin(self.xmin, self.ymax, self.dx, self.dx)

    @property
    def cell_area(self) -> float:
        return self.dx * self.dx

    @property
    def x(self) -> np.ndarray:
        """Cell-centre eastings, west to east."""
        return self.xmin + (np.arange(self.nx) + 0.5) * self.dx

    @property
    def y(self) -> np.ndarray:
        """Cell-centre northings, north to south (row order)."""
        return self.ymax - (np.arange(self.ny) + 0.5) * self.dx


def read_on_grid(path: str | Path, grid: Grid, resampling: Resampling = Resampling.average) -> np.ndarray:
    """Reproject band 1 of a raster onto ``grid``. Cells without data become NaN.

    ``average`` resampling is the right default when coarsening high-resolution DEMs
    (1-10 m) onto the model grid (25-100 m).
    """
    out = np.full(grid.shape, np.nan, dtype=np.float64)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            dst_nodata=np.nan,
            resampling=resampling,
        )
    return out


def coverage_on_grid(path: str | Path, grid: Grid) -> np.ndarray:
    """Fraction (0-1) of each grid cell covered by valid pixels of the raster."""
    with rasterio.open(path) as src:
        valid = (src.read_masks(1) > 0).astype(np.float32)
        out = np.zeros(grid.shape, dtype=np.float32)
        reproject(
            source=valid,
            destination=out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            resampling=Resampling.average,
        )
    return out.astype(np.float64)


def fill_gaps(arr: np.ndarray, max_search_cells: int = 200) -> np.ndarray:
    """Fill NaN holes by inverse-distance interpolation from surrounding valid cells."""
    valid = np.isfinite(arr)
    if valid.all():
        return arr.copy()
    filled = fillnodata(np.where(valid, arr, 0.0), mask=valid.astype(np.uint8), max_search_distance=max_search_cells)
    return np.where(valid, arr, filled)
