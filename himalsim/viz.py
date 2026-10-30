"""Plotly figures shared by the apps.

Colour roles (fixed, so a scenario keeps its colour across every chart):
    categorical  CATEGORICAL, in fixed slot order; assign slots per entity, never by rank
    magnitude    ICE_RAMP (one blue hue, light -> dark) for ice thickness
    polarity     DH_DIVERGING (red = thinning, grey = no change, blue = thickening)
    terrain      TERRAIN_GREYS, kept neutral so the ice is the focus
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from himalsim.grid import Grid

CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
ICE_RAMP = [[0.0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1.0, "#0d366b"]]
DH_DIVERGING = [[0.0, "#b3261e"], [0.25, "#e34948"], [0.5, "#d9d8d4"], [0.75, "#3987e5"], [1.0, "#104281"]]
TERRAIN_GREYS = [[0.0, "#4a4945"], [0.5, "#8f8d86"], [1.0, "#e6e5e0"]]

_LAYOUT = dict(margin=dict(l=10, r=10, t=50, b=10), font=dict(size=13),
               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")


def glacier_3d(grid: Grid, bed: np.ndarray, thickness: np.ndarray, title: str = "",
               vertical_exaggeration: float = 1.5, h_max: float | None = None, min_ice: float = 1.0) -> go.Figure:
    """Bedrock as neutral terrain, ice surface on top coloured by thickness."""
    x, y = grid.x / 1000.0, grid.y / 1000.0
    ice_surface = np.where(thickness >= min_ice, bed + thickness, np.nan)
    h_max = h_max or max(float(np.nanmax(thickness)), 1.0)

    fig = go.Figure()
    fig.add_trace(go.Surface(
        x=x, y=y, z=bed, colorscale=TERRAIN_GREYS, showscale=False, name="Bedrock",
        hovertemplate="Bed %{z:.0f} m<extra></extra>", lighting=dict(ambient=0.6, diffuse=0.8),
    ))
    fig.add_trace(go.Surface(
        x=x, y=y, z=ice_surface, surfacecolor=np.where(thickness >= min_ice, thickness, np.nan),
        colorscale=ICE_RAMP, cmin=0, cmax=h_max, name="Ice",
        colorbar=dict(title="Ice thickness (m)", len=0.6, thickness=14),
        hovertemplate="Surface %{z:.0f} m<br>Thickness %{surfacecolor:.0f} m<extra></extra>",
        lighting=dict(ambient=0.75, diffuse=0.6, specular=0.15),
    ))
    span = max(grid.nx, grid.ny) * grid.dx
    z_range = float(np.nanmax(bed + thickness) - np.nanmin(bed))
    fig.update_layout(
        title=title, height=640, **_LAYOUT,
        scene=dict(
            xaxis_title="Easting (km)", yaxis_title="Northing (km)", zaxis_title="Elevation (m)",
            aspectmode="manual",
            aspectratio=dict(x=grid.nx * grid.dx / span, y=grid.ny * grid.dx / span,
                             z=vertical_exaggeration * z_range / span),
            camera=dict(eye=dict(x=-1.2, y=-1.5, z=0.9)),
        ),
        uirevision="glacier3d",  # keep the user's camera when the year slider moves
    )
    return fig


def field_map(grid: Grid, values: np.ndarray, title: str, colorbar_title: str, colorscale,
              zmin: float | None = None, zmax: float | None = None, contour_mask: np.ndarray | None = None,
              focus_pad_m: float = 400.0) -> go.Figure:
    """Plan-view map of a 2D field (UTM km), zoomed to the data plus a margin, with an optional outline."""
    xk, yk = grid.x / 1000.0, grid.y / 1000.0
    fig = go.Figure(go.Heatmap(
        x=xk, y=yk, z=values, colorscale=colorscale, zmin=zmin, zmax=zmax,
        colorbar=dict(title=colorbar_title, thickness=14),
        hovertemplate="E %{x:.2f} km<br>N %{y:.2f} km<br>%{z:.1f}<extra></extra>",
    ))
    if contour_mask is not None:
        fig.add_trace(go.Contour(
            x=xk, y=yk, z=contour_mask.astype(float), showscale=False, hoverinfo="skip",
            contours=dict(start=0.5, end=0.5, coloring="none"), line=dict(color="#0b0b0b", width=1.5),
            name="Glacier outline",
        ))
    focus = np.isfinite(values) | (contour_mask if contour_mask is not None else False)
    if focus.any():
        rows, cols = np.nonzero(focus)
        pad = focus_pad_m / 1000.0
        fig.update_xaxes(range=[xk[cols.min()] - pad, xk[cols.max()] + pad])
        fig.update_yaxes(range=[yk[rows.max()] - pad, yk[rows.min()] + pad])
    fig.update_layout(title=title, height=460, **_LAYOUT)
    fig.update_yaxes(scaleanchor="x", scaleratio=1, title="Northing (km, UTM 45N)", showgrid=False)
    fig.update_xaxes(title="Easting (km, UTM 45N)", showgrid=False)
    return fig


def dh_map(grid: Grid, dh: np.ndarray, title: str, limit: float = 50.0, contour_mask: np.ndarray | None = None) -> go.Figure:
    return field_map(grid, dh, title, "Δh (m)", DH_DIVERGING, -limit, limit, contour_mask)


def scenario_timeseries(frame: pd.DataFrame, colors: dict[str, str]) -> go.Figure:
    """Volume, area and ELA through time as three stacked panels (never a dual axis)."""
    panels = [("volume_pct", "Volume (% of start)"), ("area_km2", "Area (km²)"), ("ela_m", "ELA (m a.s.l.)")]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=[p[1] for p in panels])
    for name, df in frame.groupby("scenario", sort=False):
        for row, (col, label) in enumerate(panels, start=1):
            fig.add_trace(go.Scatter(
                x=df["year"], y=df[col], mode="lines", name=name, legendgroup=name, showlegend=row == 1,
                line=dict(color=colors.get(name, CATEGORICAL[0]), width=2),
                hovertemplate=f"{name}<br>Year %{{x:.0f}}: %{{y:.2f}}<extra></extra>",
            ))
    fig.update_layout(height=720, hovermode="x unified", legend=dict(orientation="h", y=1.08), **_LAYOUT)
    fig.update_xaxes(title_text="Years from start", row=3, col=1, showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", zeroline=False)
    return fig


def smb_profile(z: np.ndarray, profiles: dict[str, np.ndarray], colors: dict[str, str],
                observed_range: tuple[float, float] | None = None) -> go.Figure:
    """SMB against elevation for one or more climates; where each line crosses 0 is its ELA."""
    fig = go.Figure()
    if observed_range:
        fig.add_hrect(y0=observed_range[0], y1=observed_range[1], fillcolor="rgba(128,128,128,0.12)", line_width=0,
                      annotation_text="glacier elevation range", annotation_position="top left")
    fig.add_vline(x=0, line=dict(color="rgba(128,128,128,0.7)", width=1, dash="dot"))
    for name, smb in profiles.items():
        fig.add_trace(go.Scatter(x=smb, y=z, mode="lines", name=name, line=dict(color=colors.get(name, CATEGORICAL[0]), width=2),
                                 hovertemplate=f"{name}<br>%{{y:.0f}} m: %{{x:+.2f}} m ice/yr<extra></extra>"))
    fig.update_layout(height=520, hovermode="y unified", xaxis_title="Surface mass balance (m ice / yr)",
                      yaxis_title="Elevation (m a.s.l.)", legend=dict(orientation="h", y=1.08), **_LAYOUT)
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.2)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)")
    return fig


def band_comparison(df: pd.DataFrame, title: str) -> go.Figure:
    """Observed vs modelled elevation change by elevation band (validation)."""
    fig = go.Figure()
    fig.add_vline(x=0, line=dict(color="rgba(128,128,128,0.7)", width=1, dash="dot"))
    for col, label, color in (("observed_dh", "Observed (DEM difference)", CATEGORICAL[0]),
                              ("modeled_dh", "Model", CATEGORICAL[1])):
        fig.add_trace(go.Scatter(
            x=df[col], y=df["z_mid"], mode="lines+markers", name=label,
            line=dict(color=color, width=2), marker=dict(size=9),
            customdata=df["cells"], hovertemplate=f"{label}<br>%{{y:.0f}} m: %{{x:+.1f}} m (%{{customdata}} cells)<extra></extra>",
        ))
    fig.update_layout(title=title, height=460, hovermode="y unified", xaxis_title="Elevation change since start (m)",
                      yaxis_title="Elevation band (m a.s.l.)", legend=dict(orientation="h", y=1.1), **_LAYOUT)
    fig.update_xaxes(gridcolor="rgba(128,128,128,0.2)")
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)")
    return fig


def assign_colors(names: Sequence[str], existing: dict[str, str] | None = None) -> dict[str, str]:
    """Give each new name the next free categorical slot; names already coloured keep theirs."""
    colors = dict(existing or {})
    for name in names:
        if name not in colors:
            used = set(colors.values())
            free = [c for c in CATEGORICAL if c not in used]
            colors[name] = free[0] if free else CATEGORICAL[len(colors) % len(CATEGORICAL)]
    return colors
