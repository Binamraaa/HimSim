# glacier_model_final_v14_plot_stable.py

# --- Imports ---
import streamlit as st
import plotly.graph_objs as go
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject, Resampling
import pyproj
import os
import time
from rasterio.transform import Affine
from scipy.ndimage import laplace

# --- Model Parameters (Constants and Defaults) ---
GRID_RESOLUTION = 100
BBOX_LON_MIN = 85.570; BBOX_LAT_MIN = 28.200
BBOX_LON_MAX = 85.660; BBOX_LAT_MAX = 28.275
DEM_PATH = "C:/Users/ALiEN/ICE_SHEET_DEM/DEM_and_ortho/DEM_and_ortho/1981Yala_dem_20_-10_bias_cor.tif" # <<< VERIFY PATH
UTM_CRS_EPSG = 'EPSG:32645'

# --- Simulation Defaults ---
DEFAULT_SIM_TIME_STEP = 1.0
DEFAULT_TOTAL_YEARS = 1000
DEFAULT_TEMP_ANOMALY = 0.0
DEFAULT_SNOWFALL = 0.5
DEFAULT_MELT_FACTOR = 0.003
DEFAULT_LAPSE_RATE = 0.0065
DEFAULT_BASE_TEMP_ABOVE_FREEZING = 5.0
DEFAULT_FREEZING_POINT = 0.0
DEFAULT_DIFFUSION_CONSTANT = 10.0

# --- Animation / Update Control ---
ANIMATION_DELAY_SECONDS = 0.02 # << Slightly larger delay before rerun
STEPS_PER_RERUN = 5 # << Steps per display update

# --- Physics Constants ---
MIN_THICKNESS_FOR_FLOW = 0.1 # Used by diffusion laplace boundary handling conceptually
N_EXPONENT = 3.0 # Not used by diffusion

# --- Helper function for DEM Loading and Processing (float64) ---
@st.cache_resource
def load_and_process_dem_cached(dem_path, bbox_lonlat, grid_resolution, target_crs_epsg):
    """Loads, clips, reprojects, resamples DEM. Returns float64 arrays."""
    # ... (Function body unchanged - assuming it works correctly) ...
    st.info(f"Loading DEM from {os.path.basename(dem_path)}...")
    if not os.path.exists(dem_path): st.error(f"DEM file not found: {dem_path}"); st.stop()
    lon_min, lat_min, lon_max, lat_max = bbox_lonlat
    try:
        with rasterio.open(dem_path) as src:
            if src.crs is None or src.transform is None: st.error("DEM missing CRS/Transform"); st.stop()
            if not isinstance(src.transform, Affine): st.error(f"Source transform not Affine ({type(src.transform)})."); st.stop();
            if not all(np.isfinite([src.transform.a, src.transform.e])) or src.transform.a == 0 or src.transform.e == 0: st.error(f"Source transform invalid pixel sizes: {src.transform}."); st.stop()
            if src.width <= 0 or src.height <= 0: st.error(f"Source dimensions invalid: {src.width}x{src.height}."); st.stop()
            transformer = pyproj.Transformer.from_crs("EPSG:4326", target_crs_epsg, always_xy=True)
            minx, miny = transformer.transform(float(lon_min), float(lat_min))
            maxx, maxy = transformer.transform(float(lon_max), float(lat_max))
            if minx >= maxx or miny >= maxy: st.error(f"Transformed BBOX invalid: [{minx:.0f},{maxx:.0f}]m, [{miny:.0f},{maxy:.0f}]m."); st.stop()
            nx=int(np.ceil((maxx-minx)/grid_resolution)); ny=int(np.ceil((maxy-miny)/grid_resolution))
            if nx < 2 or ny < 2: st.error(f"Grid size {nx}x{ny} too small"); st.stop()
            bed_elevation = np.empty((ny, nx), dtype=np.float64) # USE float64
            target_transform = rasterio.transform.from_bounds(minx, miny, maxx, maxy, nx, ny)
            st.info("Attempting rasterio.warp.reproject...")
            reproject(source=rasterio.band(src, 1), destination=bed_elevation,
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=target_transform, dst_crs=target_crs_epsg,
                      resampling=Resampling.bilinear, num_threads=os.cpu_count() or 1)
            st.success("Rasterio reprojection successful.")
            nodata = src.nodata
            if nodata is not None and np.isfinite(nodata):
                 nodata_mask = np.isclose(bed_elevation, nodata, atol=1e-6) if bed_elevation.dtype.kind == 'f' else (bed_elevation == nodata)
                 if np.any(nodata_mask): bed_elevation[nodata_mask] = np.nan; st.info(f"Replaced NoData ({nodata}) with NaN.")
            cols, rows = np.meshgrid(np.arange(nx), np.arange(ny))
            X_grid, Y_grid = target_transform * (cols.flatten() + 0.5, rows.flatten() + 0.5)
            X_grid = X_grid.reshape((ny, nx)).astype(np.float64); Y_grid = Y_grid.reshape((ny, nx)).astype(np.float64)
            if bed_elevation.shape != (ny, nx): st.error("Shape mismatch"); st.stop()
            return bed_elevation, X_grid, Y_grid, (minx, miny, maxx, maxy), target_transform
    except Exception as e: st.error(f"DEM Loading Error: {e}"); st.exception(e); st.stop()

# --- Helper functions for Physics ---
# ... (calculate_smb, calculate_diffusion_flow_rate, calculate_total_dhdt, calculate_volume - unchanged from v11/v12) ...
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
    smb_rate = calculate_smb(ice_thickness_np, bed_elevation_np, sim_params)
    flow_rate = calculate_diffusion_flow_rate(ice_thickness_np, bed_elevation_np, sim_params)
    total_dhdt = smb_rate + flow_rate; total_dhdt[np.isnan(bed_elevation_np)] = 0.0
    total_dhdt_cleaned = np.nan_to_num(total_dhdt, nan=0.0, posinf=0.0, neginf=0.0)
    return total_dhdt_cleaned.astype(np.float64)
def calculate_volume(ice_thickness_np, grid_resolution, bed_elevation_np):
    volume = np.sum(ice_thickness_np[(ice_thickness_np > 0) & (~np.isnan(bed_elevation_np))]) * (grid_resolution**2)
    return volume

# --- Helper function to create the 3D Plotly figure (Revised Camera) ---
# Replace the ENTIRE create_3d_figure function in your script

def create_3d_figure(ice_thickness_np, bed_elevation_np, X_grid_np, Y_grid_np, domain_bounds, current_year, total_years, sim_params, uirevision_value):
    """Creates a Plotly 3D surface figure showing ice surface and bedrock."""

    ice_thickness_np = np.array(ice_thickness_np); bed_elevation_np = np.array(bed_elevation_np)
    minx, miny, maxx, maxy = domain_bounds

    surface_elevation_np = bed_elevation_np + ice_thickness_np
    surface_elevation_np[np.isnan(bed_elevation_np)] = np.nan

    finite_bed = bed_elevation_np[np.isfinite(bed_elevation_np)]
    finite_surf = surface_elevation_np[np.isfinite(surface_elevation_np)]

    min_elev_data = np.min(finite_bed) if finite_bed.size > 0 else 0
    max_elev_data = np.max(finite_surf) if finite_surf.size > 0 else (np.max(finite_bed) if finite_bed.size > 0 else 1000)

    elev_range = max_elev_data - min_elev_data
    if elev_range <= 100: elev_range = 200 # Ensure minimum range
    plot_z_min = min_elev_data - elev_range * 0.1; plot_z_max = max_elev_data + elev_range * 0.2

    data = []
    # Define a minimum display thickness for the ice surface trace
    min_display_thick = 0.1 # meters

    # --- Bedrock Trace ---
    bed_trace = go.Surface(
        x=X_grid_np, y=Y_grid_np, z=bed_elevation_np, colorscale='viridis', name='Bedrock',
        cmin=np.nanmin(bed_elevation_np) if np.any(~np.isnan(bed_elevation_np)) else 0,
        cmax=np.nanmax(bed_elevation_np) if np.any(~np.isnan(bed_elevation_np)) else 1000,
        colorbar=dict(title='Bed Elev (m)', x=1.05),
        showscale=False, # <<< FIX: Disable colorbar for bedrock
        contours = {"z": {"show": True, "size": 100, "color": "rgba(100,100,100,0.6)"}}
    )
    data.append(bed_trace)

    # --- Ice Surface Trace ---
    ice_surface_z_masked = np.copy(surface_elevation_np)
    ice_surface_z_masked[ice_thickness_np < min_display_thick] = np.nan
    ice_surface_z_masked[np.isnan(bed_elevation_np)] = np.nan

    if np.any(~np.isnan(ice_surface_z_masked)):
        ice_trace = go.Surface(
            x=X_grid_np, y=Y_grid_np, z=ice_surface_z_masked, colorscale='Blues', name='Ice Surface',
            cmin=plot_z_min + elev_range * 0.1, cmax=plot_z_max,
            colorbar=dict(title='Ice Elev (m)', x=1.15),
            showscale=True, # <<< Keep colorbar for ice
            lighting=dict(ambient=0.7, diffuse=0.8, specular=0.2, roughness=0.6, fresnel=0.2),
            lightposition=dict(x=-10000, y=-15000, z=20000) # Keep normalized light position
        )
        data.append(ice_trace)

    fig = go.Figure(data=data)

    # --- Aspect Ratio Calculation ---
    domain_dx = maxx - minx; domain_dy = maxy - miny; plot_z_range_aspect = plot_z_max - plot_z_min
    aspect_x = 1.0; aspect_y = (domain_dy / domain_dx) if domain_dx > 0 else 1.0
    aspect_z = (plot_z_range_aspect / domain_dx * 0.5) if domain_dx > 0 and plot_z_range_aspect > 0 else 0.5
    aspect_x = max(0.1, aspect_x) if np.isfinite(aspect_x) else 1.0
    aspect_y = max(0.1, aspect_y) if np.isfinite(aspect_y) else 1.0
    aspect_z = max(0.05, aspect_z) if np.isfinite(aspect_z) else 0.5

    # --- Define Explicit Camera View ---
    # Calculate center point of the domain bounds
    center_x = (minx + maxx) / 2
    center_y = (miny + maxy) / 2
    # Center Z slightly below the middle of the *elevation data range* for better perspective
    center_z = min_elev_data + (max_elev_data - min_elev_data) * 0.3

    # Position the camera eye relative to the center and domain size
    # Look from Southwest, slightly elevated
    eye_x = center_x - domain_dx * 1.5
    eye_y = center_y - domain_dy * 1.5
    eye_z = center_z + elev_range * 1.0 # Adjust multiplier for zoom/elevation

    camera = dict(
        up=dict(x=0, y=0, z=1), # Z axis is up
        center=dict(x=center_x, y=center_y, z=center_z),
        eye=dict(x=eye_x, y=eye_y, z=eye_z)
    )

    # --- Update Layout ---
    fig.update_layout(
        title=f"Glacier Model (Year: {current_year:.0f} / {total_years:.0f})",
        scene=dict(
            xaxis_title='Easting (m)', yaxis_title='Northing (m)', zaxis_title='Elevation (m)',
            xaxis=dict(range=[minx, maxx], gridcolor='lightgrey'),
            yaxis=dict(range=[miny, maxy], gridcolor='lightgrey'),
            zaxis=dict(range=[plot_z_min, plot_z_max], gridcolor='lightgrey'),
            aspectmode='manual', aspectratio=dict(x=aspect_x, y=aspect_y, z=aspect_z),
            camera=camera # <<< Explicitly set the camera view
        ),
        margin=dict(l=10, r=10, t=60, b=10),
        uirevision=uirevision_value, # <<< Still use uirevision based on reset_counter
        # plot_bgcolor='#f9f9f9', paper_bgcolor='#fff', # Use default background
        height=700, hovermode='closest'
    )
    return fig


# --- Streamlit App Execution Flow ---
st.set_page_config(layout="wide")
st.write("This application simulates a glacier using a 2D grid (RK4, Diffusion Flow - Stabilized).")
st.markdown("---")

# --- Sidebar ---
st.sidebar.header("Model Parameters")
with st.sidebar.form("climate_params_form"):
    st.subheader("Climate Settings")
    sim_temp_anomaly = st.number_input("Temp Anomaly (°C)", value=DEFAULT_TEMP_ANOMALY, step=0.1)
    sim_snowfall_rate = st.number_input("Snowfall (m ice/yr)", value=DEFAULT_SNOWFALL, step=0.05, min_value=0.0)
    sim_melt_factor = st.number_input("Melt Factor (m/yr/°C)", value=DEFAULT_MELT_FACTOR, step=0.0001, format="%.4f", min_value=0.0)
    sim_lapse_rate = st.number_input("Lapse Rate (°C/m)", value=DEFAULT_LAPSE_RATE, step=0.0001, format="%.4f")
    sim_base_temp_above_freezing = st.number_input("Base Temp > Freezing (°C)", value=DEFAULT_BASE_TEMP_ABOVE_FREEZING, step=0.1)
    submit_climate_params = st.form_submit_button("Apply Climate")
with st.sidebar.form("flow_params_form"):
    st.subheader("Flow Settings (Diffusion)")
    sim_diffusion_constant = st.number_input("Diffusion Constant (m²/yr)", min_value=0.0, max_value=10000.0, value=DEFAULT_DIFFUSION_CONSTANT, step=1.0, format="%.1f")
    submit_flow_params = st.form_submit_button("Apply Flow")
with st.sidebar.form("time_params_form"):
     st.subheader("Simulation Time")
     sim_time_step = st.number_input("Time Step (years)", value=DEFAULT_SIM_TIME_STEP, step=0.1, min_value=0.01, max_value=50.0, format="%.2f")
     sim_total_years = st.number_input("Total Years", value=DEFAULT_TOTAL_YEARS, step=100, min_value=10)
     submit_time_params = st.form_submit_button("Apply Time")
st.sidebar.markdown("---")
st.sidebar.write(f"Grid Resolution: {GRID_RESOLUTION} m")
st.sidebar.write(f"Diffusion Constant: {sim_diffusion_constant:.1f} m²/yr")
nSteps = int(sim_total_years / sim_time_step) if sim_time_step > 0 else 0
if nSteps == 0 and sim_total_years > 0: nSteps = 1
st.sidebar.write(f"Num Steps: {nSteps}")

# --- Load DEM and Initialize State ---
st.markdown("---")
if DEM_PATH == "path/to/your/1981Yala_dem_20_-10_bias_cor.tif": st.error("UPDATE DEM_PATH!"); st.stop()
BBOX_LONLAT = (BBOX_LON_MIN, BBOX_LAT_MIN, BBOX_LON_MAX, BBOX_LAT_MAX)
try:
    st.info("Loading DEM (cached)...")
    processed_data = load_and_process_dem_cached(DEM_PATH, BBOX_LONLAT, GRID_RESOLUTION, UTM_CRS_EPSG)
    st.session_state['bed_elevation_np'] = processed_data[0]
    st.session_state['X_grid_np'] = processed_data[1]
    st.session_state['Y_grid_np'] = processed_data[2]
    st.session_state['domain_bounds'] = processed_data[3]
    Ny, Nx = st.session_state['bed_elevation_np'].shape
    st.success("DEM loaded.")
except Exception as e: st.error(f"DEM loading error: {e}"); st.stop()

if 'reset_counter' not in st.session_state: st.session_state['reset_counter'] = 0
reset_simulation = False
# Reset if state missing, shape mismatch, or any form submitted
if 'ice_thickness_np' not in st.session_state or \
   st.session_state.get('bed_elevation_np', np.array([[]])).shape != (Ny, Nx) or \
   submit_climate_params or submit_flow_params or submit_time_params:
    reset_simulation = True
# Also reset if the reset button was clicked (handle its click state here)
if 'prev_reset_clicks' not in st.session_state: st.session_state['prev_reset_clicks'] = 0
reset_button_placeholder = st.sidebar.empty() # Placeholder if needed, or put in main area
# Reset button must be defined before this check
# Let's define controls layout first

# --- Simulation Controls and Display ---
st.markdown("---")
st.subheader("Simulation Controls")
col1, col2, col3 = st.columns(3)
with col1: start_button = st.button('Start/Resume', key='start_resume', disabled=st.session_state.get('current_step', 0) >= nSteps) # Add key
with col2: stop_button = st.button('Stop', key='stop', disabled=not st.session_state.get('sim_running', False))
with col3: reset_button = st.button('Reset', key='reset', disabled=st.session_state.get('current_step', 0) == 0 and not st.session_state.get('sim_running', False))

# Check reset button click state more reliably
if reset_button: # If button was clicked in *this* rerun
    reset_simulation = True

if reset_simulation:
    st.session_state['ice_thickness_np'] = np.zeros((Ny, Nx), dtype=np.float64)
    st.session_state['current_step'] = 0
    st.session_state['sim_running'] = False
    st.session_state['ice_thickness_np'][np.isnan(st.session_state['bed_elevation_np'])] = np.nan
    st.session_state['reset_counter'] += 1
    if submit_climate_params or submit_flow_params or submit_time_params: st.info("Sim state reset due to params.")
    elif reset_button: st.info("Sim state reset by button.")
    elif 'ice_thickness_np' not in st.session_state: st.info("Initial state loaded.")


# --- Parameter Dictionary ---
current_sim_params = {
    'time_step': sim_time_step, 'total_years': sim_total_years,
    'temp_anomaly': sim_temp_anomaly, 'snowfall_rate': sim_snowfall_rate,
    'melt_factor': sim_melt_factor, 'lapse_rate': sim_lapse_rate,
    'base_temp_above_freezing': sim_base_temp_above_freezing,
    'diffusion_constant': sim_diffusion_constant,
    'grid_resolution': GRID_RESOLUTION, 'freezing_point': DEFAULT_FREEZING_POINT
}

# Handle Start/Stop Button Logic
if start_button:
    if st.session_state.get('sim_running', False): pass # Already running, button might act as pause if desired later
    else:
         if st.session_state.get('current_step', 0) < nSteps: st.session_state['sim_running'] = True; st.info("Started."); st.rerun()
         else: st.warning("Finished. Reset first.")
if stop_button:
    st.session_state['sim_running'] = False; st.info("Paused.") # Rerun happens automatically


# --- Create Placeholders ---
status_placeholder = st.empty()
volume_placeholder = st.sidebar.empty()
plot_container = st.empty()

# --- CALCULATE & DRAW DISPLAY ELEMENTS ---
current_step = st.session_state.get('current_step', 0)
current_year = current_step * current_sim_params['time_step']
total_years = current_sim_params['total_years']
is_running = st.session_state.get('sim_running', False)

status_text = f"Year: {current_year:.1f} / {total_years:.0f} (Step {current_step}/{nSteps})"
if is_running: status_text += " (Running - Diffusion)"
elif current_step >= nSteps: status_text = f"Finished (Year: {total_years:.0f})"; is_running = False # Ensure running stops
elif current_step > 0: status_text += " (Paused)"
else: status_text += " (Ready)"
status_placeholder.write(status_text)

current_volume = calculate_volume(st.session_state.get('ice_thickness_np', np.array([[]])), current_sim_params['grid_resolution'], st.session_state.get('bed_elevation_np', np.array([[]])))
volume_placeholder.write(f"Ice Volume: {current_volume:.2e} m³")

# --- Determine Uirevision Value ---
plot_uirevision_value = f"reset_state_{st.session_state.get('reset_counter', 0)}" # Tied only to reset counter

# --- Generate and draw the Plotly figure ---
fig = create_3d_figure(
    st.session_state['ice_thickness_np'], st.session_state['bed_elevation_np'],
    st.session_state['X_grid_np'], st.session_state['Y_grid_np'],
    st.session_state['domain_bounds'], current_year, total_years, current_sim_params,
    plot_uirevision_value
)
plot_container.plotly_chart(fig, use_container_width=True)


# --- PHASE 3: Simulation Animation Loop ---
if is_running and current_step < nSteps:
    steps_per_rerun = STEPS_PER_RERUN # Use constant defined at top
    steps_performed_this_rerun = 0
    instability_detected = False

    while steps_performed_this_rerun < steps_per_rerun and st.session_state.get('sim_running', False) and st.session_state['current_step'] < nSteps:

        # --- Perform Single RK4 Simulation Step ---
        H_current = st.session_state['ice_thickness_np'] # Use directly from state
        bed_current = st.session_state['bed_elevation_np']
        dt = current_sim_params['time_step']

        try:
            k1 = calculate_total_dhdt(H_current, bed_current, current_sim_params)
            valid_mask_check = ~np.isnan(k1) # Check where k1 is valid
            if not np.all(np.isfinite(k1[valid_mask_check])): instability_detected = True; print("Instability on k1"); break

            H_k2 = np.maximum(0.0, H_current + 0.5 * dt * k1); H_k2[np.isnan(bed_current)] = np.nan
            k2 = calculate_total_dhdt(H_k2, bed_current, current_sim_params)
            valid_mask_check = ~np.isnan(k2)
            if not np.all(np.isfinite(k2[valid_mask_check])): instability_detected = True; print("Instability on k2"); break

            H_k3 = np.maximum(0.0, H_current + 0.5 * dt * k2); H_k3[np.isnan(bed_current)] = np.nan
            k3 = calculate_total_dhdt(H_k3, bed_current, current_sim_params)
            valid_mask_check = ~np.isnan(k3)
            if not np.all(np.isfinite(k3[valid_mask_check])): instability_detected = True; print("Instability on k3"); break

            H_k4 = np.maximum(0.0, H_current + dt * k3); H_k4[np.isnan(bed_current)] = np.nan
            k4 = calculate_total_dhdt(H_k4, bed_current, current_sim_params)
            valid_mask_check = ~np.isnan(k4)
            if not np.all(np.isfinite(k4[valid_mask_check])): instability_detected = True; print("Instability on k4"); break

            H_new = H_current + (dt / 6.0) * (k1 + 2*k2 + 2*k3 + k4)

        except Exception as e:
            st.error(f"Error during RK4 calc: {e}"); instability_detected = True

        # Break if calculation error
        if instability_detected: st.session_state['sim_running'] = False; break

        # --- Enforce Constraints AFTER the RK4 step ---
        H_new = np.maximum(0.0, H_new); H_new[np.isnan(bed_current)] = np.nan

        # --- FINAL Instability check (Corrected to ignore expected NaNs) ---
        valid_mask_final_check = ~np.isnan(bed_current)
        if not np.all(np.isfinite(H_new[valid_mask_final_check])):
             instability_detected = True
             print(f"Instability AFTER constraints at step {st.session_state['current_step']+1}!")
             st.error(f"Non-finite values AFTER constraints at step {st.session_state['current_step']+1}")

        # Break inner loop if instability detected
        if instability_detected: st.session_state['sim_running'] = False; break

        # --- Update State if Stable ---
        st.session_state['ice_thickness_np'] = H_new.astype(np.float64) # Update state
        st.session_state['current_step'] += 1
        steps_performed_this_rerun += 1


    # --- AFTER the inner loop finishes ---
    if instability_detected:
        st.error(f"Simulation unstable at Step {st.session_state['current_step']}. Try smaller Time Step or Diffusion Constant.")

    # Trigger next rerun if simulation should continue
    if st.session_state.get('sim_running', False) and st.session_state['current_step'] < nSteps:
        # time.sleep(ANIMATION_DELAY_SECONDS) # Optional small delay if needed
        st.rerun()


# --- Final Status/Info Messages at the bottom ---
st.markdown("---")
final_step = st.session_state.get('current_step', 0)
final_total_years = current_sim_params.get('total_years', DEFAULT_TOTAL_YEARS)
if final_step >= nSteps: st.success(f"Simulation completed after {final_total_years:.0f} years.")
elif not st.session_state.get('sim_running', False) and final_step > 0: # Check local instability flag if needed
     # Instability message is shown when it happens
     if 'instability_detected' not in locals() or not instability_detected: # Check if flag exists and is False
         st.info(f"Simulation paused at Year {final_step * current_sim_params['time_step']:.1f}.")

# --- END OF SCRIPT ---