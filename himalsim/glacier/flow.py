"""Ice flow with the Shallow Ice Approximation (SIA).

In a thin glacier the driving stress is balanced locally by basal drag, so ice
flux depends only on the local thickness H and surface slope grad(S):

    q = -D grad(S),    D = (Gamma_d H^(n+2) + Gamma_s H^n) |grad(S)|^(n-1)

    Gamma_d = 2 A (rho g)^n / (n + 2)      internal deformation (Glen's law)
    Gamma_s = f_s (rho g)^n                basal sliding (Oerlemans-type law)

and mass conservation gives  dH/dt = SMB - div(q).

The equation is a nonlinear diffusion: ice "diffuses" down the surface slope,
faster where it is thick and steep. We discretise it with the classic Mahaffy
(1976) staggered-grid scheme: D and q are computed on cell faces, so the flux
leaving one cell is exactly the flux entering its neighbour. This conserves
mass, unlike taking np.gradient of a cell-centred flux.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from himalsim.constants import G, GLEN_A_TEMPERATE, GLEN_N, RHO_ICE, SECONDS_PER_YEAR


@dataclass(frozen=True)
class FlowParams:
    glen_a: float = GLEN_A_TEMPERATE  # Pa-3 s-1, ice softness; larger = faster flow
    sliding: float = 0.0  # f_s, Pa-3 m2 s-1; Oerlemans (1997) used 5.7e-20; 0 disables sliding
    n: float = GLEN_N

    @property
    def gamma_deformation(self) -> float:
        """Gamma_d in m^-n yr^-1 (per year so that D comes out in m2/yr)."""
        return 2.0 * self.glen_a * (RHO_ICE * G) ** self.n / (self.n + 2.0) * SECONDS_PER_YEAR

    @property
    def gamma_sliding(self) -> float:
        return self.sliding * (RHO_ICE * G) ** self.n * SECONDS_PER_YEAR


def _face_diffusivity(h_face: np.ndarray, grad2: np.ndarray, p: FlowParams) -> np.ndarray:
    n = p.n
    return (p.gamma_deformation * h_face ** (n + 2) + p.gamma_sliding * h_face ** n) * grad2 ** ((n - 1) / 2)


def sia_fluxes(thickness: np.ndarray, bed: np.ndarray, dx: float, p: FlowParams):
    """Ice fluxes on cell faces (m2/yr).

    Returns ``(qx, qy, d_max)`` where ``qx`` has shape (ny, nx-1) for the faces
    between columns j and j+1, ``qy`` has shape (ny-1, nx) for faces between rows
    i and i+1, and ``d_max`` is the largest diffusivity (sets the stable time step).
    Positive flux points toward increasing index.
    """
    h = thickness
    s = bed + h

    # Surface slope across each face, plus the transverse slope averaged onto the face
    ds_dx_c = np.gradient(s, dx, axis=1)
    ds_dy_c = np.gradient(s, dx, axis=0)

    ds_dx_xf = (s[:, 1:] - s[:, :-1]) / dx
    ds_dy_xf = 0.5 * (ds_dy_c[:, 1:] + ds_dy_c[:, :-1])
    h_xf = 0.5 * (h[:, 1:] + h[:, :-1])
    d_x = _face_diffusivity(h_xf, ds_dx_xf**2 + ds_dy_xf**2, p)
    qx = -d_x * ds_dx_xf

    ds_dy_yf = (s[1:, :] - s[:-1, :]) / dx
    ds_dx_yf = 0.5 * (ds_dx_c[1:, :] + ds_dx_c[:-1, :])
    h_yf = 0.5 * (h[1:, :] + h[:-1, :])
    d_y = _face_diffusivity(h_yf, ds_dx_yf**2 + ds_dy_yf**2, p)
    qy = -d_y * ds_dy_yf

    d_max = max(float(d_x.max(initial=0.0)), float(d_y.max(initial=0.0)))
    return qx, qy, d_max


def flux_divergence(qx: np.ndarray, qy: np.ndarray, dx: float) -> np.ndarray:
    """div(q) at cell centres. Domain-edge faces carry zero flux (closed boundary)."""
    ny, nx = qy.shape[0] + 1, qx.shape[1] + 1
    div = np.zeros((ny, nx))
    div[:, :-1] += qx
    div[:, 1:] -= qx
    div[:-1, :] += qy
    div[1:, :] -= qy
    return div / dx


def limit_outflow(qx: np.ndarray, qy: np.ndarray, thickness: np.ndarray, dx: float, dt: float):
    """Scale down fluxes so no cell exports more ice in ``dt`` than it contains.

    At steep glacier margins the Mahaffy scheme can overshoot: a thin cell next to a
    steep drop gets a large face-averaged flux and is drained below zero. Clipping
    H back to zero would then *create* ice. Limiting each cell's outgoing fluxes
    instead keeps H >= 0 and conserves mass exactly, because each face flux is
    shared by the donor and receiver cells.
    """
    out = np.zeros_like(thickness)
    out[:, :-1] += np.maximum(qx, 0.0)
    out[:, 1:] += np.maximum(-qx, 0.0)
    out[:-1, :] += np.maximum(qy, 0.0)
    out[1:, :] += np.maximum(-qy, 0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        factor = np.where(out * dt > thickness * dx, thickness * dx / (out * dt), 1.0)

    qx = np.where(qx > 0, qx * factor[:, :-1], qx * factor[:, 1:])
    qy = np.where(qy > 0, qy * factor[:-1, :], qy * factor[1:, :])
    return qx, qy


def stable_timestep(d_max: float, dx: float, cfl: float = 0.5, dt_max: float = 1.0) -> float:
    """Largest explicit time step (yr) that keeps the diffusion scheme stable.

    For 2D explicit diffusion the limit is dt <= dx^2 / (4 D). ``cfl`` < 1 adds
    a safety margin because D changes during the step.
    """
    if d_max <= 0.0:
        return dt_max
    return min(dt_max, cfl * dx * dx / (4.0 * d_max))
