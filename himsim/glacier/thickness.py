"""Initial ice thickness: what lies between the DEM surface and the bedrock.

A DEM shows only the ice *surface*. To get the bed we need ice thickness, which
is rarely measured. We use the "perfect plasticity" estimate (Nye 1952;
Cuffey & Paterson 2010, ch. 8): ice deforms until the basal shear stress
reaches a yield value tau, so

    H = tau / (rho g sin(alpha))

where alpha is the surface slope. The yield stress follows the empirical
relation of Haeberli & Hoelzle (1995), which grows with the glacier's elevation
range. It is a rough estimate (+/- 30-50 %), but it gives a physically shaped bed.

``initial_thickness`` combines two independent estimates: the *pattern* comes from
perfect plasticity (thick where the surface is flat, thin on steep parts and at the
margin), and the *total volume* comes from volume-area scaling. For Yala, plasticity
alone gives ~24 m mean thickness, too thin to survive the observed 1981-2015 thinning.
Global thickness products (Farinotti et al. 2019; Millan et al. 2022) are better
and can be plugged in later.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter

from himsim.constants import G, RHO_ICE


def haeberli_hoelzle_tau(elevation_range_m: float) -> float:
    """Basal yield stress (Pa) from glacier elevation range (Haeberli & Hoelzle 1995)."""
    dz_km = min(max(elevation_range_m / 1000.0, 0.0), 1.6)
    tau_bar = 0.005 + 1.598 * dz_km - 0.435 * dz_km**2
    return min(tau_bar, 1.5) * 1.0e5


def perfect_plasticity_thickness(surface: np.ndarray, mask: np.ndarray, dx: float, tau: float | None = None,
                                 smoothing_m: float = 200.0, min_slope_deg: float = 4.0,
                                 margin_taper_m: float = 150.0) -> np.ndarray:
    """Ice thickness (m) inside ``mask``; zero outside.

    - The surface is smoothed over ``smoothing_m`` (using glacier cells only) because ice
      responds to slopes averaged over several ice thicknesses, not pixel-scale bumps.
    - The slope is floored at ``min_slope_deg`` so flat areas don't get unrealistically thick ice.
    - Thickness tapers to zero within ``margin_taper_m`` of the glacier edge.
    """
    if tau is None:
        tau = haeberli_hoelzle_tau(float(np.ptp(surface[mask])))

    # Smooth using glacier cells only (normalised convolution). Including the terrain
    # beyond the outline would blend ridge crests into the glacier and fake flat, thick ice.
    sigma = max(smoothing_m / dx, 0.5)
    inside = mask & np.isfinite(surface)
    weight = gaussian_filter(inside.astype(np.float64), sigma)
    smooth = gaussian_filter(np.where(inside, surface, 0.0), sigma) / np.maximum(weight, 1e-6)
    gy, gx = np.gradient(smooth, dx)
    slope = np.arctan(np.hypot(gx, gy))
    slope = np.maximum(slope, np.deg2rad(min_slope_deg))

    h = tau / (RHO_ICE * G * np.sin(slope))

    dist_to_edge = distance_transform_edt(mask) * dx
    h *= np.sqrt(np.clip(dist_to_edge / margin_taper_m, 0.0, 1.0))
    return np.where(mask, h, 0.0)


def volume_area_scaling(area_m2: float, c: float = 0.034, gamma: float = 1.375) -> float:
    """Glacier volume (m3) from area alone (Bahr et al. 1997; c, gamma for valley glaciers)."""
    return c * (area_m2 / 1e6) ** gamma * 1e9


def initial_thickness(surface: np.ndarray, mask: np.ndarray, dx: float, method: str = "scaled") -> np.ndarray:
    """Ice thickness for model start-up.

    method:
        "plasticity"  perfect plasticity alone
        "scaled"      plasticity pattern rescaled to the volume-area-scaling volume (default)
    """
    h = perfect_plasticity_thickness(surface, mask, dx)
    if method == "plasticity":
        return h
    if method == "scaled":
        target = volume_area_scaling(mask.sum() * dx * dx)
        return h * target / (h.sum() * dx * dx)
    raise ValueError(f"unknown thickness method: {method!r}")
