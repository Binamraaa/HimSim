import numpy as np
import pytest

from himsim.glacier.flow import FlowParams, flux_divergence, limit_outflow, sia_fluxes, stable_timestep


def _step_flow_only(h, bed, dx, p, t_end):
    t = 0.0
    while t < t_end:
        qx, qy, d_max = sia_fluxes(h, bed, dx, p)
        dt = min(stable_timestep(d_max, dx, cfl=0.5, dt_max=50.0), t_end - t)
        qx, qy = limit_outflow(qx, qy, h, dx, dt)
        h = np.maximum(h - dt * flux_divergence(qx, qy, dx), 0.0)
        t += dt
    return h


def test_outflow_limiter_keeps_thickness_positive():
    """Thin ice on a ledge above thick ice gets a large face-averaged flux and must not be drained below zero."""
    bed = np.zeros((5, 5))
    bed[:, :2] = 200.0  # rock ledge
    h = np.full((5, 5), 100.0)
    h[:, :2] = 1.0  # thin ice on the ledge
    qx, qy, _ = sia_fluxes(h, bed, 50.0, FlowParams())
    dt = 1.0
    raw = h - dt * flux_divergence(qx, qy, 50.0)
    assert raw.min() < 0  # without the limiter the margin overshoots
    qx, qy = limit_outflow(qx, qy, h, 50.0, dt)
    limited = h - dt * flux_divergence(qx, qy, 50.0)
    assert limited.min() >= -1e-12
    assert limited.sum() == pytest.approx(h.sum())


def test_flat_ice_does_not_flow():
    h = np.full((20, 20), 100.0)
    qx, qy, d_max = sia_fluxes(h, np.zeros_like(h), 50.0, FlowParams())
    assert np.allclose(qx, 0) and np.allclose(qy, 0)


def test_flow_conserves_mass():
    rng = np.random.default_rng(0)
    bed = rng.normal(0, 20, (40, 40)).cumsum(axis=0)
    h = np.zeros((40, 40))
    h[10:30, 10:30] = 80.0
    qx, qy, _ = sia_fluxes(h, bed, 50.0, FlowParams())
    assert abs(flux_divergence(qx, qy, 50.0).sum()) < 1e-9 * np.abs(qx).sum()


def test_ice_flows_downhill():
    bed = np.tile(np.linspace(1000.0, 0.0, 30), (10, 1))  # slopes down toward increasing column index
    h = np.full_like(bed, 50.0)
    qx, _, _ = sia_fluxes(h, bed, 100.0, FlowParams())
    assert (qx[2:-2, 2:-2] > 0).all()


def test_stable_timestep_shrinks_with_diffusivity():
    assert stable_timestep(0.0, 50.0) == 1.0
    assert stable_timestep(1e4, 50.0) < stable_timestep(1e3, 50.0)


def halfar(r, t, p, h0, r0):
    """Halfar (1981) similarity solution for a dome of ice on a flat bed with no mass balance (n = 3)."""
    t0 = (1.0 / (18.0 * p.gamma_deformation)) * (7.0 / 4.0) ** 3 * r0**4 / h0**7
    ratio = t0 / t
    inner = np.clip(1.0 - (ratio ** (1 / 18) * r / r0) ** (4 / 3), 0.0, None)
    return h0 * ratio ** (1 / 9) * inner ** (3 / 7), t0


def test_halfar_dome():
    """Compare the numerical scheme with the exact solution: the standard SIA benchmark (Bueler et al. 2005)."""
    p = FlowParams()
    dx, n = 500.0, 61
    x = (np.arange(n) - n // 2) * dx
    r = np.hypot(*np.meshgrid(x, x))
    h0, r0 = 300.0, 10_000.0
    h_start, t0 = halfar(r, 1.0, p, h0, r0)
    h_start, _ = halfar(r, t0, p, h0, r0)

    h_num = _step_flow_only(h_start.copy(), np.zeros_like(r), dx, p, t_end=t0)  # from t0 to 2*t0
    h_exact, _ = halfar(r, 2 * t0, p, h0, r0)

    centre = n // 2
    assert h_num[centre, centre] == pytest.approx(h_exact[centre, centre], rel=0.03)
    assert h_num.sum() == pytest.approx(h_start.sum(), rel=1e-6)  # no mass gained or lost
    inside = h_exact > 0.5 * h_exact.max()
    assert np.abs(h_num[inside] - h_exact[inside]).mean() < 0.03 * h0
