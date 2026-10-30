# glacier_model_dash_final_v2.py

# --- Imports ---
import dash
# If using Dash version < 2.11, use: from dash.dependencies import Input, Output, State
# For Dash version >= 2.11, use:
from dash import dcc, html, Input, Output, State, callback, no_update
import plotly.graph_objs as go
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject, Resampling
import pyproj
import os
# import time # Not used in main loop, Dash interval controls timing
from rasterio.transform import Affine
from scipy.ndimage import laplace
import json # For serializing numpy arrays for dcc.Store

# --- Model Parameters (Constants and Defaults) ---
GRID_RESOLUTION = 100 # meters
BBOX_LON_MIN = 85.570; BBOX_LAT_MIN = 28.200
BBOX_LON_MAX = 85.660; BBOX_LAT_MAX = 28.275
# !!! ACTION REQUIRED: VERIFY YOUR DEM PATH !!!
DEM_PATH = "C:/Users/ALiEN/ICE_SHEET_DEM/DEM_and_ortho/DEM_and_ortho/1981Yala_dem_20_-10_bias_cor.tif"
UTM_CRS_EPSG = 'EPSG:32645'

# --- Simulation Defaults (Conservative for Stability) ---
DEFAULT_SIM_TIME_STEP = 1.0      # Years
DEFAULT_TOTAL_YEARS = 1000     # Years
DEFAULT_TEMP_ANOMALY = 0.0
DEFAULT_SNOWFALL = 0.5
DEFAULT_MELT_FACTOR = 0.003
DEFAULT_LAPSE_RATE = 0.0065
DEFAULT_BASE_TEMP_ABOVE_FREEZING = 5.0
DEFAULT_FREEZING_POINT = 0.0 # Reference
DEFAULT_DIFFUSION_CONSTANT = 10.0 # m²/year (Start low)

# Animation / Update Interval
INTERVAL_MS = 200 # milliseconds (How often the simulation callback runs - slower for stability)
STEPS_PER_INTERVAL = 5 # <<< Simulation steps per interval tick (Adjust for performance)

# --- Helper function for DEM Loading ---
def load_initial_data(dem_path, bbox_lonlat, grid_resolution, target_crs_epsg):
    """Loads DEM, returns float64 arrays. Simplified for global load."""
    print(f"Attempting to load DEM from {os.path.basename(dem_path)}...")
    if not os.path.exists(dem_path): raise FileNotFoundError(f"DEM file not found: {dem_path}")
    lon_min, lat_min, lon_max, lat_max = bbox_lonlat
    try:
        with rasterio.open(dem_path) as src:
            if src.crs is None or src.transform is None: raise ValueError("DEM missing CRS/Transform")
            transformer = pyproj.Transformer.from_crs("EPSG:4326", target_crs_epsg, always_xy=True)
            minx, miny = transformer.transform(float(lon_min), float(lat_min))
            maxx, maxy = transformer.transform(float(lon_max), float(lat_max))
            if minx >= maxx or miny >= maxy: raise ValueError("Invalid BBOX range")
            nx=int(np.ceil((maxx-minx)/grid_resolution)); ny=int(np.ceil((maxy-miny)/grid_resolution))
            if nx < 2 or ny < 2: raise ValueError("Grid size too small")
            bed_elevation = np.empty((ny, nx), dtype=np.float64)
            target_transform = rasterio.transform.from_bounds(minx, miny, maxx, maxy, nx, ny)
            reproject(source=rasterio.band(src, 1), destination=bed_elevation,
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=target_transform, dst_crs=target_crs_epsg,
                      resampling=Resampling.bilinear, num_threads=os.cpu_count() or 1)
            nodata = src.nodata
            if nodata is not None and np.isfinite(nodata):
                 nodata_mask = np.isclose(bed_elevation, nodata, atol=1e-6) if bed_elevation.dtype.kind == 'f' else (bed_elevation == nodata)
                 if np.any(nodata_mask): bed_elevation[nodata_mask] = np.nan
            cols, rows = np.meshgrid(np.arange(nx), np.arange(ny))
            X_grid, Y_grid = target_transform * (cols.flatten() + 0.5, rows.flatten() + 0.5)
            X_grid = X_grid.reshape((ny, nx)).astype(np.float64); Y_grid = Y_grid.reshape((ny, nx)).astype(np.float64)
            print("DEM loaded and processed successfully.")
            return bed_elevation, X_grid, Y_grid, (minx, miny, maxx, maxy)
    except Exception as e: print(f"DEM Loading Error: {e}"); raise e

# --- Load Initial Data at App Startup ---
try:
    initial_bed_elevation_np, initial_X_grid_np, initial_Y_grid_np, initial_domain_bounds = load_initial_data(DEM_PATH, (BBOX_LON_MIN, BBOX_LAT_MIN, BBOX_LON_MAX, BBOX_LAT_MAX), GRID_RESOLUTION, UTM_CRS_EPSG)
    initial_Ny, initial_Nx = initial_bed_elevation_np.shape
    initial_ice_thickness_np = np.zeros((initial_Ny, initial_Nx), dtype=np.float64)
    initial_ice_thickness_np[np.isnan(initial_bed_elevation_np)] = np.nan
except Exception as e_load: # Catch loading error explicitly
    print(f"CRITICAL: Halting app startup due to DEM loading error: {e_load}")
    initial_bed_elevation_np = np.array([[0,0],[0,0]], dtype=np.float64) # Dummy data to allow app to load and show error
    initial_X_grid_np = np.array([[0,1],[0,1]], dtype=np.float64)
    initial_Y_grid_np = np.array([[0,0],[1,1]], dtype=np.float64)
    initial_domain_bounds = (0,0,1,1)
    initial_ice_thickness_np = np.zeros((2,2), dtype=np.float64)
    # In a production app, you'd display a more user-friendly error page.
    # For now, if DEM load fails, the plot will be based on dummy data and an error will be in console.

# --- Helper functions for Physics ---
def calculate_smb(ice_thickness_np, bed_elevation_np, sim_params):
    ice_thickness_np = np.array(ice_thickness_np, dtype=np.float64); bed_elevation_np = np.array(bed_elevation_np, dtype=np.float64)
    surface_elevation_np = bed_elevation_np + ice_thickness_np
    smb = np.zeros_like(ice_thickness_np, dtype=np.float64); valid_mask = ~np.isnan(bed_elevation_np)
    if np.any(valid_mask):
        valid_surf_elev = surface_elevation_np[valid_mask]; accumulation_rate_valid = sim_params['snowfall_rate'] * np.ones_like(valid_surf_elev)
        temp_above_freezing_valid = (sim_params['base_temp_above_freezing'] + sim_params['temp_anomaly']) - sim_params['lapse_rate'] * valid_surf_elev
        melt_rate_valid = sim_params['melt_factor'] * np.maximum(0.0, temp_above_freezing_valid)
        smb_valid = accumulation_rate_valid - melt_rate_valid; smb[valid_mask] = smb_valid
    return smb.astype(np.float64)
def calculate_diffusion_flow_rate(ice_thickness_np, bed_elevation_np, sim_params):
    ice_thickness_np = np.array(ice_thickness_np, dtype=np.float64); bed_elevation_np = np.array(bed_elevation_np, dtype=np.float64)
    thickness_for_laplace = np.nan_to_num(ice_thickness_np, nan=0.0)
    laplacian_H = laplace(thickness_for_laplace, mode='constant', cval=0.0) / (sim_params['grid_resolution']**2)
    diffusion_rate = sim_params['diffusion_constant'] * laplacian_H
    diffusion_rate[np.isnan(bed_elevation_np)] = 0.0
    return diffusion_rate.astype(np.float64)
def calculate_total_dhdt(ice_thickness_np, bed_elevation_np, sim_params):
    ice_thickness_np = np.array(ice_thickness_np, dtype=np.float64); bed_elevation_np = np.array(bed_elevation_np, dtype=np.float64)
    smb_rate = calculate_smb(ice_thickness_np, bed_elevation_np, sim_params); flow_rate = calculate_diffusion_flow_rate(ice_thickness_np, bed_elevation_np, sim_params) # Using Diffusion
    total_dhdt = smb_rate + flow_rate; total_dhdt[np.isnan(bed_elevation_np)] = 0.0
    total_dhdt_cleaned = np.nan_to_num(total_dhdt, nan=0.0, posinf=0.0, neginf=0.0) # Final safety
    return total_dhdt_cleaned.astype(np.float64)
def calculate_volume(ice_thickness_np, grid_resolution, bed_elevation_np):
    volume = np.sum(ice_thickness_np[(ice_thickness_np > 0) & (~np.isnan(bed_elevation_np))]) * (grid_resolution**2)
    return volume

# --- Helper function to create the 3D Plotly figure ---
def create_3d_figure(ice_thickness_np, bed_elevation_np, X_grid_np, Y_grid_np, domain_bounds, current_year, total_years, sim_params, uirevision_value):
    ice_thickness_np = np.array(ice_thickness_np); bed_elevation_np = np.array(bed_elevation_np)
    minx, miny, maxx, maxy = domain_bounds
    surface_elevation_np = bed_elevation_np + ice_thickness_np
    surface_elevation_np[np.isnan(bed_elevation_np)] = np.nan
    finite_bed = bed_elevation_np[np.isfinite(bed_elevation_np)]; finite_surf = surface_elevation_np[np.isfinite(surface_elevation_np)]
    min_elev_data = np.min(finite_bed) if finite_bed.size > 0 else 0
    max_elev_data = np.max(finite_surf) if finite_surf.size > 0 else (np.max(finite_bed) if finite_bed.size > 0 else 1000)
    elev_range = max_elev_data - min_elev_data
    if elev_range <= 100: elev_range = 200
    plot_z_min = min_elev_data - elev_range * 0.1; plot_z_max = max_elev_data + elev_range * 0.2
    data = []; min_display_thick = 0.1
    bed_trace = go.Surface(x=X_grid_np, y=Y_grid_np, z=bed_elevation_np, colorscale='viridis', name='Bedrock',
                           cmin=np.nanmin(bed_elevation_np) if np.any(~np.isnan(bed_elevation_np)) else 0,
                           cmax=np.nanmax(bed_elevation_np) if np.any(~np.isnan(bed_elevation_np)) else 1000,
                           colorbar=dict(title='Bed Elev (m)', x=1.05), showscale=False,
                           contours = {"z": {"show": True, "size": 100, "color": "rgba(100,100,100,0.6)"}})
    data.append(bed_trace)
    ice_surface_z_masked = np.copy(surface_elevation_np)
    ice_surface_z_masked[ice_thickness_np < min_display_thick] = np.nan
    ice_surface_z_masked[np.isnan(bed_elevation_np)] = np.nan
    if np.any(~np.isnan(ice_surface_z_masked)):
        ice_trace = go.Surface(x=X_grid_np, y=Y_grid_np, z=ice_surface_z_masked, colorscale='Blues', name='Ice Surface',
                               cmin=plot_z_min + elev_range * 0.1, cmax=plot_z_max,
                               colorbar=dict(title='Ice Elev (m)', x=1.15), showscale=True,
                               lighting=dict(ambient=0.7, diffuse=0.8, specular=0.2, roughness=0.6, fresnel=0.2),
                               lightposition=dict(x=-10000, y=-15000, z=20000)) # Normalized values
        data.append(ice_trace)
    fig = go.Figure(data=data)
    domain_dx = maxx - minx; domain_dy = maxy - miny; plot_z_range_aspect = plot_z_max - plot_z_min
    aspect_x = 1.0; aspect_y = (domain_dy / domain_dx) if domain_dx > 0 else 1.0
    aspect_z = (plot_z_range_aspect / domain_dx * 0.5) if domain_dx > 0 and plot_z_range_aspect > 0 else 0.5
    aspect_x = max(0.1, aspect_x) if np.isfinite(aspect_x) else 1.0
    aspect_y = max(0.1, aspect_y) if np.isfinite(aspect_y) else 1.0
    aspect_z = max(0.05, aspect_z) if np.isfinite(aspect_z) else 0.5
    camera = dict(up=dict(x=0, y=0, z=1), center=dict(x= (minx+maxx)/2, y= (miny+maxy)/2, z=min_elev_data + elev_range * 0.3),
                  eye=dict(x=(minx+maxx)/2 - domain_dx*1.5, y=(miny+maxy)/2 - domain_dy*1.5, z=plot_z_min + elev_range * 1.0))
    fig.update_layout(title=f"Glacier Model (Year: {current_year:.0f} / {total_years:.0f})",
        scene=dict(xaxis_title='Easting (m)', yaxis_title='Northing (m)', zaxis_title='Elevation (m)',
                   xaxis=dict(range=[minx, maxx], gridcolor='lightgrey'), yaxis=dict(range=[miny, maxy], gridcolor='lightgrey'), zaxis=dict(range=[plot_z_min, plot_z_max], gridcolor='lightgrey'),
                   aspectmode='manual', aspectratio=dict(x=aspect_x, y=aspect_y, z=aspect_z), camera=camera),
        margin=dict(l=10, r=10, t=60, b=10), uirevision=uirevision_value, height=700, hovermode='closest')
    return fig


# --- Setup Dash App ---
app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
server = app.server

# --- Initial Parameter Dictionary (for dcc.Store) ---
initial_sim_params = {
    'time_step': DEFAULT_SIM_TIME_STEP, 'total_years': DEFAULT_TOTAL_YEARS,
    'temp_anomaly': DEFAULT_TEMP_ANOMALY, 'snowfall_rate': DEFAULT_SNOWFALL,
    'melt_factor': DEFAULT_MELT_FACTOR, 'lapse_rate': DEFAULT_LAPSE_RATE,
    'base_temp_above_freezing': DEFAULT_BASE_TEMP_ABOVE_FREEZING,
    'diffusion_constant': DEFAULT_DIFFUSION_CONSTANT,
    'grid_resolution': GRID_RESOLUTION, 'freezing_point': DEFAULT_FREEZING_POINT
}

# --- App Layout ---
app.layout = html.Div([
    html.H1("2D Glacier Model (Plotly Dash - Diffusion Flow)", style={'textAlign': 'center'}),
    dcc.Store(id='ice-thickness-store', data=json.dumps(initial_ice_thickness_np.tolist())),
    dcc.Store(id='bed-elevation-store', data=json.dumps(initial_bed_elevation_np.tolist())),
    dcc.Store(id='x-grid-store', data=json.dumps(initial_X_grid_np.tolist())),
    dcc.Store(id='y-grid-store', data=json.dumps(initial_Y_grid_np.tolist())),
    dcc.Store(id='domain-bounds-store', data=initial_domain_bounds),
    dcc.Store(id='current-step-store', data=0),
    dcc.Store(id='sim-params-store', data=initial_sim_params),
    dcc.Store(id='reset-counter-store', data=0),
    html.Div(className='row', children=[
        html.Div(className='three columns', style={'padding': '10px', 'borderRight': '1px solid #ddd'}, children=[
            html.H3("Parameters"),
            html.Label("Temp Anomaly (°C)"), dcc.Input(id='param-temp-anomaly', type='number', value=initial_sim_params['temp_anomaly'], step=0.1),
            html.Label("Snowfall (m ice/yr)"), dcc.Input(id='param-snowfall', type='number', value=initial_sim_params['snowfall_rate'], step=0.05, min=0.0),
            html.Label("Melt Factor (m/yr/°C)"), dcc.Input(id='param-melt-factor', type='number', value=initial_sim_params['melt_factor'], step=0.0001, min=0.0),
            html.Label("Lapse Rate (°C/m)"), dcc.Input(id='param-lapse-rate', type='number', value=initial_sim_params['lapse_rate'], step=0.0001),
            html.Label("Base Temp > Freezing (°C)"), dcc.Input(id='param-base-temp', type='number', value=initial_sim_params['base_temp_above_freezing'], step=0.1),
            html.Hr(),
            html.Label("Diffusion Constant (m²/yr)"), dcc.Input(id='param-diffusion-coeff', type='number', value=initial_sim_params['diffusion_constant'], step=1.0, min=0.0),
            html.Hr(),
            html.Label("Time Step (years)"), dcc.Input(id='param-time-step', type='number', value=initial_sim_params['time_step'], step=0.1, min=0.01),
            html.Label("Total Years"), dcc.Input(id='param-total-years', type='number', value=initial_sim_params['total_years'], step=100, min=10),
            html.Button('Apply Parameters & Reset Sim', id='apply-reset-button', n_clicks=0, style={'marginTop': '15px', 'width': '100%'}),
            html.Hr(),
            html.Div(id='display-volume', style={'marginTop': '10px'})
        ]),
        html.Div(className='nine columns', style={'padding': '10px'}, children=[
            html.Div(id='status-display', style={'textAlign': 'center', 'marginBottom': '10px', 'fontSize': '1.2em'}),
            html.Div(className='row', children=[
                 html.Button('Start/Resume', id='start-button', n_clicks=0, style={'width': '30%', 'margin': '1%'}),
                 html.Button('Stop', id='stop-button', n_clicks=0, disabled=True, style={'width': '30%', 'margin': '1%'}),
                 html.Button('Reset', id='reset-button', n_clicks=0, disabled=True, style={'width': '30%', 'margin': '1%'})
            ], style={'textAlign': 'center', 'marginBottom': '10px'}),
            dcc.Graph(id='glacier-plot', style={'height': '75vh'})
        ])
    ]),
    dcc.Interval(id='simulation-interval', interval=INTERVAL_MS, n_intervals=0, disabled=True)
])

# --- Callbacks ---

@callback( Output('sim-params-store', 'data'),
    [Input(f'param-{param}', 'value') for param in ['temp-anomaly', 'snowfall', 'melt-factor', 'lapse-rate', 'base-temp', 'diffusion-coeff', 'time-step', 'total-years']],
    State('sim-params-store', 'data'))
def update_parameters(temp_anom, snowfall, melt, lapse, base_temp, diff_coeff, dt, t_total, current_params):
    updated_params = current_params.copy()
    updated_params['temp_anomaly'] = temp_anom if temp_anom is not None else DEFAULT_TEMP_ANOMALY
    updated_params['snowfall_rate'] = snowfall if snowfall is not None and snowfall >= 0 else DEFAULT_SNOWFALL
    updated_params['melt_factor'] = melt if melt is not None and melt >= 0 else DEFAULT_MELT_FACTOR
    updated_params['lapse_rate'] = lapse if lapse is not None else DEFAULT_LAPSE_RATE
    updated_params['base_temp_above_freezing'] = base_temp if base_temp is not None else DEFAULT_BASE_TEMP_ABOVE_FREEZING
    updated_params['diffusion_constant'] = diff_coeff if diff_coeff is not None and diff_coeff >=0 else DEFAULT_DIFFUSION_CONSTANT
    updated_params['time_step'] = dt if dt is not None and dt > 0 else DEFAULT_SIM_TIME_STEP
    updated_params['total_years'] = t_total if t_total is not None and t_total >= 10 else DEFAULT_TOTAL_YEARS
    return updated_params

@callback(
    [Output('simulation-interval', 'disabled'), Output('start-button', 'children'),
     Output('start-button', 'disabled'), Output('stop-button', 'disabled'), Output('reset-button', 'disabled'),
     Output('ice-thickness-store', 'data', allow_duplicate=True),
     Output('current-step-store', 'data', allow_duplicate=True),
     Output('reset-counter-store', 'data', allow_duplicate=True)],
    [Input('start-button', 'n_clicks'), Input('stop-button', 'n_clicks'),
     Input('reset-button', 'n_clicks'), Input('apply-reset-button', 'n_clicks')],
    [State('simulation-interval', 'disabled'), State('current-step-store', 'data'),
     State('sim-params-store', 'data'), State('reset-counter-store', 'data')],
    prevent_initial_call=True)
def control_simulation(start_clicks, stop_clicks, reset_clicks, apply_clicks,
                        interval_disabled, current_step, sim_params, reset_counter):
    triggered_id = dash.ctx.triggered_id
    time_step = sim_params.get('time_step', DEFAULT_SIM_TIME_STEP)
    total_years = sim_params.get('total_years', DEFAULT_TOTAL_YEARS)
    n_steps_total = int(total_years / time_step) if time_step > 0 else 0
    is_running = not interval_disabled; is_finished = current_step >= n_steps_total
    out_interval_disabled = interval_disabled; out_start_text = 'Start/Resume'
    out_start_disabled = is_running or is_finished; out_stop_disabled = not is_running
    out_reset_disabled = current_step == 0 and not is_running
    out_ice_thickness = dash.no_update; out_current_step = dash.no_update
    out_reset_counter = reset_counter
    if triggered_id in ['reset-button', 'apply-reset-button']:
        out_interval_disabled = True; out_ice_thickness = json.dumps(initial_ice_thickness_np.tolist())
        out_current_step = 0; out_reset_counter = reset_counter + 1
        out_start_text = 'Start/Resume'; out_start_disabled = False
        out_stop_disabled = True; out_reset_disabled = True
    elif triggered_id == 'start-button':
        if is_running:
            out_interval_disabled = True; out_start_text = 'Resume'
            out_start_disabled = False; out_stop_disabled = True
            out_reset_disabled = False if current_step > 0 else True
        else:
             if not is_finished:
                 out_interval_disabled = False; out_start_text = 'Pause'
                 out_start_disabled = False; out_stop_disabled = False; out_reset_disabled = False
             else: out_start_text = 'Start/Resume'; out_start_disabled = True
    elif triggered_id == 'stop-button':
         if is_running:
             out_interval_disabled = True; out_start_text = 'Resume'
             out_start_disabled = False; out_stop_disabled = True
             out_reset_disabled = False if current_step > 0 else True
    return (out_interval_disabled, out_start_text, out_start_disabled, out_stop_disabled, out_reset_disabled,
            out_ice_thickness, out_current_step, out_reset_counter)

@callback(
    [Output('glacier-plot', 'figure', allow_duplicate=True),
     Output('status-display', 'children', allow_duplicate=True),
     Output('display-volume', 'children', allow_duplicate=True),
     Output('ice-thickness-store', 'data'), Output('current-step-store', 'data'),
     Output('simulation-interval', 'disabled', allow_duplicate=True),
     Output('reset-counter-store', 'data')],
    [Input('simulation-interval', 'n_intervals'), Input('reset-counter-store', 'data')], # Add reset_counter as Input
    [State('ice-thickness-store', 'data'), State('bed-elevation-store', 'data'),
     State('x-grid-store', 'data'), State('y-grid-store', 'data'),
     State('domain-bounds-store', 'data'), State('current-step-store', 'data'),
     State('sim-params-store', 'data')],
    prevent_initial_call=False # <<< RUN ON INITIAL LOAD (triggered by reset_counter_store init)
)
def update_simulation_and_plot(n_intervals, reset_counter_val, # n_intervals is from interval, reset_counter_val from store
                                ice_json, bed_json, x_json, y_json, bounds, current_step, sim_params):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    ice_thickness_np = np.array(json.loads(ice_json), dtype=np.float64)
    bed_elevation_np = np.array(json.loads(bed_json), dtype=np.float64)
    X_grid_np = np.array(json.loads(x_json), dtype=np.float64)
    Y_grid_np = np.array(json.loads(y_json), dtype=np.float64)
    domain_bounds = bounds

    time_step = sim_params.get('time_step', DEFAULT_SIM_TIME_STEP)
    total_years = sim_params.get('total_years', DEFAULT_TOTAL_YEARS)
    n_steps_total = int(total_years / time_step) if time_step > 0 else 0

    instability_detected = False
    sim_should_stop_interval = False # Default to not stopping interval

    # Only run simulation steps if triggered by interval AND interval is enabled
    # (interval disabled state is handled by control_simulation callback)
    if triggered_id == 'simulation-interval' and not dash.callback_context.outputs_list[5]['disabled']: # Check if interval is truly enabled
        for _ in range(STEPS_PER_INTERVAL):
            if current_step >= n_steps_total: sim_should_stop_interval = True; break
            H_current = ice_thickness_np
            try:
                k1 = calculate_total_dhdt(H_current, bed_elevation_np, sim_params)
                if not np.all(np.isfinite(k1[~np.isnan(k1)])): instability_detected = True; break
                H_k2 = np.maximum(0.0, H_current + 0.5 * time_step * k1); H_k2[np.isnan(bed_elevation_np)] = np.nan
                k2 = calculate_total_dhdt(H_k2, bed_elevation_np, sim_params)
                if not np.all(np.isfinite(k2[~np.isnan(k2)])): instability_detected = True; break
                H_k3 = np.maximum(0.0, H_current + 0.5 * time_step * k2); H_k3[np.isnan(bed_elevation_np)] = np.nan
                k3 = calculate_total_dhdt(H_k3, bed_elevation_np, sim_params)
                if not np.all(np.isfinite(k3[~np.isnan(k3)])): instability_detected = True; break
                H_k4 = np.maximum(0.0, H_current + time_step * k3); H_k4[np.isnan(bed_elevation_np)] = np.nan
                k4 = calculate_total_dhdt(H_k4, bed_elevation_np, sim_params)
                if not np.all(np.isfinite(k4[~np.isnan(k4)])): instability_detected = True; break
                H_new = H_current + (time_step / 6.0) * (k1 + 2*k2 + 2*k3 + k4)
            except Exception as e: print(f"Error RK4: {e}"); instability_detected = True
            if instability_detected: break
            H_new = np.maximum(0.0, H_new); H_new[np.isnan(bed_elevation_np)] = np.nan
            valid_mask_final = ~np.isnan(bed_elevation_np)
            if not np.all(np.isfinite(H_new[valid_mask_final])): instability_detected = True; break
            ice_thickness_np = H_new; current_step += 1
        if instability_detected: sim_should_stop_interval = True # Stop interval if unstable

    # This part runs for initial plot, after reset, and after each interval batch
    current_year = current_step * time_step
    status_text = f"Year: {current_year:.1f} / {total_years:.0f} (Step {current_step}/{n_steps_total})"
    if instability_detected: status_text += " (Stopped - Instability!)"
    elif sim_should_stop_interval or current_step >= n_steps_total: status_text = f"Finished (Year: {total_years:.0f})"; sim_should_stop_interval = True
    elif not dash.callback_context.outputs_list[5]['disabled']: status_text += " (Running - Diffusion)" # Check actual interval state
    else: status_text += " (Ready/Paused)"

    current_volume = calculate_volume(ice_thickness_np, sim_params['grid_resolution'], bed_elevation_np)
    volume_display = f"Total Ice Volume: {current_volume:.2e} m³"
    uirevision_value = f"reset_state_{reset_counter}" # Use reset_counter from state
    fig = create_3d_figure(ice_thickness_np, bed_elevation_np, X_grid_np, Y_grid_np,
                           domain_bounds, current_year, total_years, sim_params, uirevision_value)
    return (fig, status_text, volume_display, json.dumps(ice_thickness_np.tolist()),
            current_step, sim_should_stop_interval, reset_counter)


# --- Run the App ---
if __name__ == '__main__':
    print("Starting Dash app...")
    if initial_bed_elevation_np is None: print("Cannot start: Initial data failed to load.")
    else: app.run(debug=True, port=8051)