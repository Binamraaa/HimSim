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

from himsim.grid import Grid

CATEGORICAL = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
ICE_RAMP = [[0.0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1.0, "#0d366b"]]
DH_DIVERGING = [[0.0, "#b3261e"], [0.25, "#e34948"], [0.5, "#d9d8d4"], [0.75, "#3987e5"], [1.0, "#104281"]]
TERRAIN_GREYS = [[0.0, "#4a4945"], [0.5, "#8f8d86"], [1.0, "#e6e5e0"]]
INK = "#52514e"  # neutral line for the modelled past and reference lines (not a categorical slot)
GRID = "rgba(128,128,128,0.2)"

_LAYOUT = dict(margin=dict(l=10, r=10, t=50, b=10), font=dict(size=13),
               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")


def glacier_animation(grid: Grid, bed: np.ndarray, frames: Sequence[tuple[str, np.ndarray]], focus: np.ndarray,
                      title: str = "", h_max: float | None = None, vertical_exaggeration: float = 1.5,
                      min_ice: float = 1.0, pad_cells: int = 8, frame_ms: int = 400) -> go.Figure:
    """3D glacier with a Play button and a time slider. ``frames`` = [(label, thickness), ...].

    The view is cropped to ``focus`` (e.g. the glacier outline) plus any cell that holds ice in
    some frame, with a margin. Only the ice surface changes between frames, so playback stays
    smooth in the browser.
    """
    focus = focus | np.any([h >= min_ice for _, h in frames], axis=0)
    rows, cols = np.nonzero(focus)
    r0, r1 = max(rows.min() - pad_cells, 0), min(rows.max() + pad_cells + 1, grid.ny)
    c0, c1 = max(cols.min() - pad_cells, 0), min(cols.max() + pad_cells + 1, grid.nx)
    x, y, b = grid.x[c0:c1] / 1000.0, grid.y[r0:r1] / 1000.0, bed[r0:r1, c0:c1]
    h_max = h_max or max(max(float(h.max()) for _, h in frames), 1.0)

    def ice(h):
        h = h[r0:r1, c0:c1]
        on = h >= min_ice
        return np.round(np.where(on, b + h, np.nan), 1), np.round(np.where(on, h, np.nan), 1)

    z_first, c_first = ice(frames[0][1])
    fig = go.Figure([
        go.Surface(x=x, y=y, z=b, colorscale=TERRAIN_GREYS, showscale=False, name="Rock",
                   hovertemplate="Rock %{z:.0f} m<extra></extra>", lighting=dict(ambient=0.6, diffuse=0.8)),
        go.Surface(x=x, y=y, z=z_first, surfacecolor=c_first, colorscale=ICE_RAMP, cmin=0, cmax=h_max, name="Ice",
                   colorbar=dict(title="Ice thickness (m)", len=0.6, thickness=14),
                   hovertemplate="Ice surface %{z:.0f} m<br>Ice %{surfacecolor:.0f} m thick<extra></extra>",
                   lighting=dict(ambient=0.75, diffuse=0.6, specular=0.15)),
    ])
    frame_list = []
    for label, h in frames:
        z, c = ice(h)
        frame_list.append(go.Frame(name=label, traces=[1], data=[go.Surface(z=z, surfacecolor=c)],
                                   layout=dict(title=dict(text=f"{title}{label}"))))
    fig.frames = frame_list

    still = dict(mode="immediate", frame=dict(duration=0, redraw=True), transition=dict(duration=0))
    play = dict(mode="immediate", fromcurrent=True, transition=dict(duration=0), frame=dict(duration=frame_ms, redraw=True))
    span = max(len(x), len(y)) * grid.dx
    z_low = float(b.min())
    z_top = max(float(np.nanmax(b + h[r0:r1, c0:c1])) for _, h in frames)
    fig.update_layout(
        title=f"{title}{frames[0][0]}", height=600, **_LAYOUT,
        scene=dict(
            xaxis_title="East (km)", yaxis_title="North (km)", zaxis_title="Height (m)",
            zaxis=dict(range=[z_low, z_top]), aspectmode="manual",
            aspectratio=dict(x=len(x) * grid.dx / span, y=len(y) * grid.dx / span,
                             z=vertical_exaggeration * (z_top - z_low) / span),
            camera=dict(eye=dict(x=-1.25, y=-1.45, z=0.85)),
        ),
        uirevision="glacier3d",
        updatemenus=[dict(type="buttons", direction="left", x=0.0, y=0.02, xanchor="left", yanchor="top",
                          pad=dict(r=8, t=8), showactive=False, buttons=[
                              dict(label="\u25b6 Play", method="animate", args=[None, play]),
                              dict(label="Pause", method="animate", args=[[None], still]),
                          ])],
        sliders=[dict(active=0, x=0.18, len=0.82, y=0.02, yanchor="top", pad=dict(t=8),
                      currentvalue=dict(visible=False),
                      steps=[dict(label=f.name, method="animate", args=[[f.name], still]) for f in frame_list])],
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


def climate_annual_chart(annual: pd.DataFrame, trend_start: int, trend_end: int, trend_per_decade: float) -> go.Figure:
    """Yearly mean temperature (with trend line) and yearly precipitation, as two stacked panels."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=["Average temperature (°C)", "Total precipitation (mm)"])
    fig.add_trace(go.Scatter(x=annual.index, y=annual["t_c"], mode="lines+markers", name="Yearly mean",
                             line=dict(color=CATEGORICAL[1], width=2), marker=dict(size=5),
                             hovertemplate="%{x}: %{y:.2f} °C<extra></extra>"), row=1, col=1)
    seg = annual.loc[trend_start:trend_end]
    fit = np.polyfit(seg.index.values, seg["t_c"].values, 1)
    fig.add_trace(go.Scatter(x=seg.index, y=np.polyval(fit, seg.index.values), mode="lines",
                             name=f"Trend {trend_start}–{trend_end}: {trend_per_decade:+.2f} °C/decade",
                             line=dict(color="#52514e", width=2, dash="dash"), hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Bar(x=annual.index, y=annual["p_mm"], name="Yearly precipitation", marker_color=CATEGORICAL[0],
                         hovertemplate="%{x}: %{y:.0f} mm<extra></extra>", showlegend=False), row=2, col=1)
    fig.update_layout(height=560, hovermode="x unified", legend=dict(orientation="h", y=1.1), bargap=0.15, **_LAYOUT)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)")
    fig.update_xaxes(showgrid=False)
    return fig


def climate_monthly_chart(clim: pd.DataFrame, month_names: Sequence[str]) -> go.Figure:
    """Average year: monthly temperature and precipitation as two side-by-side panels."""
    fig = make_subplots(rows=1, cols=2, horizontal_spacing=0.12,
                        subplot_titles=["Temperature (°C)", "Precipitation (mm)"])
    fig.add_trace(go.Scatter(x=list(month_names), y=clim["t_c"], mode="lines+markers", line=dict(color=CATEGORICAL[1], width=2),
                             marker=dict(size=8), hovertemplate="%{x}: %{y:.1f} °C<extra></extra>", showlegend=False), row=1, col=1)
    fig.add_hline(y=0, line=dict(color="rgba(128,128,128,0.7)", width=1, dash="dot"), row=1, col=1)
    fig.add_trace(go.Bar(x=list(month_names), y=clim["p_mm"], marker_color=CATEGORICAL[0],
                         hovertemplate="%{x}: %{y:.0f} mm<extra></extra>", showlegend=False), row=1, col=2)
    fig.update_layout(height=360, bargap=0.2, **_LAYOUT)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)")
    return fig


def volume_story(past: pd.DataFrame, futures: dict[str, pd.DataFrame], colors: dict[str, str],
                 measured: Sequence[tuple[int, float, float, str]] = (), baseline: str | None = None,
                 today: int | None = None) -> go.Figure:
    """Ice volume (million m³) from the first survey to the end of the scenarios, in one chart.

    ``past`` and each future frame come from ``RunResult.to_frame``. ``measured`` adds field
    estimates as (year, value_km3, upper_error_km3, label) markers. ``baseline`` is drawn dashed in INK.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=past["calendar_year"], y=past["volume_km3"] * 1000, mode="lines", name="The past (model)",
                             line=dict(color=INK, width=3), hovertemplate="%{x:.0f}: %{y:.0f} million m³<extra></extra>"))
    for name, df in futures.items():
        is_base = name == baseline
        fig.add_trace(go.Scatter(
            x=df["calendar_year"], y=df["volume_km3"] * 1000, mode="lines", name=name,
            line=dict(color=INK if is_base else colors.get(name, CATEGORICAL[0]), width=2, dash="dash" if is_base else None),
            hovertemplate=f"{name}<br>%{{x:.0f}}: %{{y:.0f}} million m³<extra></extra>"))
    for year, value, up, label in measured:
        fig.add_trace(go.Scatter(x=[year], y=[value * 1000], mode="markers", name=label,
                                 marker=dict(symbol="diamond", size=12, color=CATEGORICAL[2],
                                             line=dict(color="#ffffff", width=2)),
                                 error_y=dict(type="data", symmetric=False, array=[up * 1000], arrayminus=[0],
                                              color=CATEGORICAL[2], thickness=2, width=6),
                                 hovertemplate=f"{label}<br>%{{x}}: %{{y:.0f}} million m³<extra></extra>"))
    if today is not None:
        fig.add_vline(x=today, line=dict(color="rgba(128,128,128,0.6)", width=1, dash="dot"))
        fig.add_annotation(x=today, y=1.0, yref="paper", text="today", showarrow=False, yshift=10, font=dict(size=12))
    fig.update_layout(height=430, hovermode="x unified", yaxis_title="Ice in the glacier (million m³)",
                      legend=dict(orientation="h", y=-0.15), **_LAYOUT)
    fig.update_yaxes(gridcolor=GRID, rangemode="tozero")
    fig.update_xaxes(showgrid=False)
    return fig


def yearly_mass_balance_chart(df: pd.DataFrame) -> go.Figure:
    """Measured (with error bars) vs modelled glacier-wide mass balance for each year."""
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color="rgba(128,128,128,0.7)", width=1, dash="dot"))
    fig.add_trace(go.Scatter(x=df["year"] - 0.12, y=df["measured"], mode="markers", name="Measured (stakes)",
                             marker=dict(size=11, color=CATEGORICAL[0]),
                             error_y=dict(type="data", array=df["uncertainty"], color=CATEGORICAL[0], thickness=2),
                             hovertemplate="%{y:+.2f} m w.e. (measured)<extra></extra>"))
    fig.add_trace(go.Scatter(x=df["year"] + 0.12, y=df["model"], mode="markers", name="Model",
                             marker=dict(size=11, color=CATEGORICAL[1], symbol="square"),
                             hovertemplate="%{y:+.2f} m w.e. (model)<extra></extra>"))
    fig.update_layout(height=380, hovermode="x unified", yaxis_title="Mass balance (m of water per year)",
                      legend=dict(orientation="h", y=1.12), **_LAYOUT)
    fig.update_xaxes(dtick=1, showgrid=False)
    fig.update_yaxes(gridcolor=GRID)
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
