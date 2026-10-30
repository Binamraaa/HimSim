"""Time-stepping glacier model: dH/dt = SMB - div(q).

``simulate`` runs one scenario and returns a ``RunResult`` with yearly
diagnostics (volume, area, ELA, ...) and thickness snapshots for visualisation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from himalsim.glacier.climate import ClimateParams, Scenario
from himalsim.glacier.flow import FlowParams, flux_divergence, limit_outflow, sia_fluxes, stable_timestep
from himalsim.glacier.smb import annual_smb, equilibrium_line_altitude

ICE_THRESHOLD_M = 1.0  # cells thinner than this don't count as glacier for area/extent


@dataclass
class RunResult:
    scenario: Scenario
    climate: ClimateParams
    flow: FlowParams
    years: np.ndarray
    volume: np.ndarray  # m3
    area: np.ndarray  # m2
    ela: np.ndarray  # m a.s.l.
    smb_glacier: np.ndarray  # glacier-wide SMB, m ice / yr
    max_thickness: np.ndarray  # m
    snapshot_years: list[float] = field(default_factory=list)
    snapshots: list[np.ndarray] = field(default_factory=list)  # thickness fields
    n_steps: int = 0
    outflow_m3: float = 0.0  # ice that left through the domain edge

    @property
    def final_thickness(self) -> np.ndarray:
        return self.snapshots[-1]

    @property
    def volume_remaining_pct(self) -> float:
        return 100.0 * self.volume[-1] / self.volume[0] if self.volume[0] > 0 else float("nan")

    @property
    def year_vanished(self) -> float | None:
        """First year with (almost) no glacier left, or None if it survives the run."""
        gone = np.nonzero(self.area < 0.01 * self.area[0])[0]
        return float(self.years[gone[0]]) if gone.size else None

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame({
            "scenario": self.scenario.name,
            "year": self.years,
            "volume_km3": self.volume / 1e9,
            "volume_pct": 100.0 * self.volume / self.volume[0] if self.volume[0] > 0 else np.nan,
            "area_km2": self.area / 1e6,
            "ela_m": self.ela,
            "smb_glacier_m_ice_per_yr": self.smb_glacier,
            "max_thickness_m": self.max_thickness,
        })


def simulate(bed: np.ndarray, h0: np.ndarray, dx: float, climate: ClimateParams, scenario: Scenario,
             flow: FlowParams = FlowParams(), accumulation_mask: np.ndarray | None = None,
             snapshot_every: int = 5, cfl: float = 0.5, dt_max: float = 1.0,
             progress: Callable[[float], None] | None = None) -> RunResult:
    """Run ``scenario`` from initial thickness ``h0`` on ``bed``.

    ``accumulation_mask`` limits where new ice can form: outside it, SMB is capped at
    zero, so the glacier can still flow downhill and melt there, but no new glaciers
    grow on surrounding peaks. Without this, steep ridges above the ELA would pile up
    snow that in reality avalanches off.

    The time step adapts every step to the stability limit, and steps are
    shortened so that yearly diagnostics land exactly on whole years. Ice that
    reaches the outermost row/column of the domain is removed and counted as
    ``outflow_m3``, so the domain should be large enough that this stays ~0.
    """
    cell_area = dx * dx
    h = np.where(np.isfinite(h0), h0, 0.0).astype(np.float64)
    edge = np.zeros(h.shape, dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True

    rec: dict[str, list[float]] = {k: [] for k in ("years", "volume", "area", "ela", "smb", "hmax")}
    snapshot_years: list[float] = []
    snapshots: list[np.ndarray] = []

    def record(t: float) -> None:
        dt_, pf = scenario.temp_delta(t), scenario.precip_factor(t)
        ice = h > ICE_THRESHOLD_M
        surf = bed + h
        rec["years"].append(t)
        rec["volume"].append(float(h.sum() * cell_area))
        rec["area"].append(float(ice.sum() * cell_area))
        rec["ela"].append(equilibrium_line_altitude(climate, dt_, pf))
        rec["smb"].append(float(annual_smb(surf[ice], climate, dt_, pf).mean()) if ice.any() else float("nan"))
        rec["hmax"].append(float(h.max()))
        if round(t) % snapshot_every == 0 or round(t) >= scenario.years:
            snapshot_years.append(t)
            snapshots.append(h.copy())

    t, n_steps, outflow = 0.0, 0, 0.0
    record(t)
    next_record = 1.0
    while t < scenario.years - 1e-9:
        qx, qy, d_max = sia_fluxes(h, bed, dx, flow)
        dt = min(stable_timestep(d_max, dx, cfl, dt_max), next_record - t)
        qx, qy = limit_outflow(qx, qy, h, dx, dt)
        smb = annual_smb(bed + h, climate, scenario.temp_delta(t), scenario.precip_factor(t))
        if accumulation_mask is not None:
            smb = np.where(accumulation_mask, smb, np.minimum(smb, 0.0))

        h = np.maximum(h + dt * (smb - flux_divergence(qx, qy, dx)), 0.0)
        outflow += float(h[edge].sum() * cell_area)
        h[edge] = 0.0

        t += dt
        n_steps += 1
        if t >= next_record - 1e-9:
            t = next_record
            record(t)
            next_record += 1.0
            if progress is not None:
                progress(min(t / scenario.years, 1.0))

    return RunResult(
        scenario=scenario, climate=climate, flow=flow,
        years=np.array(rec["years"]), volume=np.array(rec["volume"]), area=np.array(rec["area"]),
        ela=np.array(rec["ela"]), smb_glacier=np.array(rec["smb"]), max_thickness=np.array(rec["hmax"]),
        snapshot_years=snapshot_years, snapshots=snapshots, n_steps=n_steps, outflow_m3=outflow,
    )
