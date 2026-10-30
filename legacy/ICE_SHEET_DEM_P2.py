# glacier_model_2d_phase2_v4.py

# --- Imports (All imports MUST be at the top level with NO indentation) ---
import streamlit as st
import plotly.graph_objs as go
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject, Resampling # <--- ENSURE THIS IS HERE
import pyproj
import os
import time # Needed for Phase 3 animation
from rasterio.transform import Affine # For isinstance check


# --- Model Parameters (Constants and Defaults - top level) ---
GRID_RESOLUTION = 100 # meters

# Geographic bounding box for Yala Glacier (Approximate)
# VERIFY these coordinates cover YOUR DEM file
BBOX_LON_MIN = 85.570
BBOX_LAT_MIN = 28.200
BBOX_LON_MAX = 85.660
BBOX_LAT_MAX = 28.275

# PATH TO YOUR DEM FILE (Set correctly!)
DEM_PATH = "C:/Users/ALiEN/ICE_SHEET_DEM/DEM_and_ortho/DEM_and_ortho/1981Yala_dem_20_-10_bias_cor.tif" # <<< VERIFY THIS PATH IS CORRECT

UTM_CRS_EPSG = 'EPSG:32645' # UTM Zone 45N

# Default/Initial Simulation Parameters
DEFAULT_SIM_TIME_STEP = 100
DEFAULT_TOTAL_YEARS = 50000
DEFAULT_TEMP_ANOMALY = 0.0
DEFAULT_SNOWFALL = 0.5
DEFAULT_MELT_FACTOR = 0.003
DEFAULT_LAPSE_RATE = 0.0065
DEFAULT_BASE_TEMP_ABOVE_FREEZING = 5.0
DEFAULT_FREEZING_POINT = 0.0

DEFAULT_FLOW_RATE_FACTOR_EXP = -15.0
MIN_THICKNESS_FOR_FLOW = 0.1
N_EXPONENT = 3.0


# --- Helper function for DEM Loading and Processing (Cached) ---
# This function must be defined AT THE TOP LEVEL (no indentation before def)
@st.cache_resource
def load_and_process_dem_cached(dem_path, bbox_lonlat, grid_resolution, target_crs_epsg):
    """Loads, clips, reprojects, and resamples DEM."""
    st.info(f"Attempting to load DEM from {os.path.basename(dem_path)}...")
    if not os.path.exists(dem_path):
        st.error(f"Error: DEM file not found at: {dem_path}"); st.stop()
    lon_min, lat_min, lon_max, lat_max = bbox_lonlat

    try:
        with rasterio.open(dem_path) as src:
            # --- Source Info Checks ---
            if src.crs is None: st.error("Error: Source DEM metadata missing CRS."); st.stop()
            if src.transform is None: st.error("Error: Source DEM metadata missing transform."); st.stop()
            if not isinstance(src.transform, Affine): st.error(f"Error: Source DEM transform not Affine ({type(src.transform)})."); st.stop()
            if not all(np.isfinite([src.transform.a, src.transform.e])) or src.transform.a == 0 or src.transform.e == 0: st.error(f"Error: Source transform invalid pixel sizes: {src.transform}."); st.stop()
            if src.width <= 0 or src.height <= 0: st.error(f"Error: Source DEM dimensions invalid: {src.width}x{src.height}."); st.stop()

            # --- Transform Bbox to Target CRS ---
            transformer_wgs84_to_target = pyproj.Transformer.from_crs("EPSG:4326", target_crs_epsg, always_xy=True)
            bbox_lonlat_float = (float(lon_min), float(lat_min), float(lon_max), float(lat_max))
            if not all(np.isfinite(bbox_lonlat_float)): st.error(f"Error: Input BBOX has non-finite values: {bbox_lonlat_float}."); st.stop()

            minx, miny = transformer_wgs84_to_target.transform(bbox_lonlat_float[0], bbox_lonlat_float[1])
            maxx, maxy = transformer_wgs84_to_target.transform(bbox_lonlat_float[2], bbox_lonlat_float[3])

            if minx >= maxx or miny >= maxy: st.error(f"Error: Transformed BBOX coordinates result in invalid range: [{minx:.0f},{maxx:.0f}]m, [{miny:.0f},{maxy:.0f}]m. Check BBOX order/values."); st.stop()

            # --- Define Target Grid ---
            grid_width = maxx - minx
            grid_height = maxy - miny
            nx = int(np.ceil(grid_width / grid_resolution))
            ny = int(np.ceil(grid_height / grid_resolution))

            if nx < 2 or ny < 2: st.error(f"Error: Calculated grid size {nx}x{ny} too small (< 2x2). Adjust BBOX/GRID_RESOLUTION."); st.stop()

            bed_elevation = np.empty((ny, nx), dtype=np.float32)

            # --- Define Target Transform ---
            try:
                 target_transform = rasterio.transform.from_bounds(minx, miny, maxx, maxy, nx, ny)
            except Exception as e: st.error(f"Error creating target transform: {e}"); st.stop()

            # --- Reproject and Resample ---
            st.info("Attempting rasterio.warp.reproject...")
            try:
                reproject(
                    source=rasterio.band(src, 1),
                    destination=bed_elevation,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=target_transform,
                    dst_crs=target_crs_epsg,
                    resampling=Resampling.bilinear, # Resampling is defined at top
                    num_threads=os.cpu_count() or 1
                )
                st.success("Rasterio reprojection successful.")
            except Exception as e:
                 st.error(f"--- ERROR during rasterio.warp.reproject ---")
                 st.exception(e) # Show traceback
                 st.info("Debug Info: Check Source/Target Transforms and CRSs.")
                 st.write(f"- Source CRS: {src.crs}, Transform: {src.transform}")
                 st.write(f"- Target CRS: {target_crs_epsg}, Transform: {target_transform}")
                 st.info("Potential issues: Source file invalid, BBOX mismatch, library linking.")
                 st.stop() # Stop on reprojection error

            # --- Handle NoData ---
            nodata = src.nodata
            if nodata is not None and np.isfinite(nodata) and np.any(np.isfinite(bed_elevation)):
                 nodata_mask = np.isclose(bed_elevation, nodata) if bed_elevation.dtype.kind == 'f' else (bed_elevation == nodata)
                 if np.any(nodata_mask):
                     bed_elevation[nodata_mask] = np.nan
                     st.info(f"Replaced {np.sum(nodata_mask)} NoData values ({nodata}) with NaN.")

            # --- Generate Grid Coordinates ---
            cols, rows = np.meshgrid(np.arange(nx), np.arange(ny))
            X_grid, Y_grid = target_transform * (cols.flatten() + 0.5, rows.flatten() + 0.5)
            X_grid = X_grid.reshape((ny, nx))
            Y_grid = Y_grid.reshape((ny, nx))

            # --- Final Checks ---
            if bed_elevation.shape != (ny, nx) or X_grid.shape != (ny, nx) or Y_grid.shape != (ny, nx): st.error("Internal Error: Generated arrays have incorrect shape."); st.stop()
            if not np.any(np.isfinite(bed_elevation)): st.warning("Warning: Loaded DEM region contains no finite elevation data. Check BBOX and DEM.");

            return bed_elevation, X_grid, Y_grid, (minx, miny, maxx, maxy), target_transform

    except Exception as e:
        st.error(f"An unexpected error occurred during DEM loading or processing (outside reproject):")
        st.exception(e) # Show traceback
        st.stop()


# --- Helper functions for Physics (Phase 2 Implementations) ---
# These functions must be defined AT THE TOP LEVEL (no indentation before def)
def calculate_smb(ice_thickness_np, bed_elevation_np, sim_params):
    """
    Calculates Surface Mass Balance (Accumulation - Ablation).
    Units: meters ice eq. / year
    """
    ice_thickness_np = np.array(ice_thickness_np)
    bed_elevation_np = np.array(bed_elevation_np)
    surface_elevation_np = bed_elevation_np + ice_thickness_np
    smb = np.zeros_like(ice_thickness_np)
    valid_mask = ~np.isnan(bed_elevation_np)
    if np.any(valid_mask):
        valid_surf_elev = surface_elevation_np[valid_mask]
        accumulation_rate_valid = sim_params['snowfall_rate'] * np.ones_like(valid_surf_elev)
        temp_above_freezing_valid = (sim_params['base_temp_above_freezing'] + sim_params['temp_anomaly']) - sim_params['lapse_rate'] * valid_surf_elev
        melt_rate_valid = sim_params['melt_factor'] * np.maximum(0.0, temp_above_freezing_valid)
        smb_valid = accumulation_rate_valid - melt_rate_valid
        smb[valid_mask] = smb_valid
    return smb

def calculate_sia_flow_rate(ice_thickness_np, bed_elevation_np, sim_params):
    """
    Calculates the rate of thickness change due to ice flow (SIA).
    dH/dt = -nabla dot q. Units: meters / year
    """
    ice_thickness_np = np.array(ice_thickness_np)
    bed_elevation_np = np.array(bed_elevation_np)
    Ny, Nx = ice_thickness_np.shape
    surface_elevation_np = bed_elevation_np + ice_thickness_np
    surface_elevation_np[np.isnan(bed_elevation_np)] = np.nan # Propagate NaN from bed

    dSdy, dSdx = np.gradient(surface_elevation_np, sim_params['grid_resolution'])

    H_eff = np.maximum(0.0, ice_thickness_np)
    # can_flow_mask = (H_eff >= MIN_THICKNESS_FOR_FLOW) & (~np.isnan(bed_elevation_np)) # Mask where bed is NaN is crucial

    # Simplify mask check: flow calculation only where ice thickness is positive and bed is not NaN
    can_flow_mask = (ice_thickness_np > 0.0) & (~np.isnan(bed_elevation_np))
    # Note: This simplified mask might miss flow initiation where H becomes positive but very small.
    # Using H_eff >= MIN_THICKNESS_FOR_FLOW is better but need to be careful with indexing/slicing.
    # Let's refine mask using MIN_THICKNESS_FOR_FLOW on H_eff:
    can_flow_mask = (H_eff >= MIN_THICKNESS_FOR_FLOW) & (~np.isnan(bed_elevation_np)) # Back to better mask


    q_x = np.zeros_like(ice_thickness_np)
    q_y = np.zeros_like(ice_thickness_np)

    if np.any(can_flow_mask):
        # Get valid gradients and H values only within the mask
        dSdx_masked = dSdx[can_flow_mask]
        dSdy_masked = dSdy[can_flow_mask]
        H_masked = H_eff[can_flow_mask]

        # Ensure gradients themselves are not NaN on the flow mask (propagated from surrounding NaNs)
        # Mask based on gradient finiteness
        gradient_finite_mask = np.isfinite(dSdx_masked) & np.isfinite(dSdy_masked)

        # Apply flux calculation only where mask is True AND gradients are finite
        q_x[can_flow_mask] = - sim_params['flow_rate_factor'] * (H_masked[gradient_finite_mask]**(N_EXPONENT + 2)) * dSdx_masked[gradient_finite_mask]
        q_y[can_flow_mask] = - sim_params['flow_rate_factor'] * (H_masked[gradient_finite_mask]**(N_EXPONENT + 2)) * dSdy_masked[gradient_finite_mask]


    # --- Calculate Divergence of Flux ---
    # Calculate divergence over the full grid after setting NaNs in q to 0 for the gradient part
    q_x_for_div = np.nan_to_num(q_x, nan=0.0)
    q_y_for_div = np.nan_to_num(q_y, nan=0.0)

    # Use the actual grid resolution for gradient spacing
    # np.gradient returns dy then dx
    dqx_dx, dqx_dy = np.gradient(q_x_for_div, sim_params['grid_resolution'])
    dqy_dx, dqy_dy = np.gradient(q_y_for_div, sim_params['grid_resolution'])

    # Divergence = dqx/dx + dqy/dy
    divergence_q = dqx_dx + dqy_dy

    # Change in thickness due to flow is - Divergence(q)
    dhdt_flow = -divergence_q

    # Ensure dhdt_flow is 0 in areas where bed is NaN (no land/ice there)
    dhdt_flow[np.isnan(bed_elevation_np)] = 0.0 # Set explicitly to 0


    return dhdt_flow

def calculate_total_dhdt(ice_thickness_np, bed_elevation_np, sim_params):
    """
    Calculates the total rate of thickness change (dH/dt = SMB + Flow_term).
    Flow_term is - div(q).
    Units: meters / year
    """
    ice_thickness_np = np.array(ice_thickness_np)
    bed_elevation_np = np.array(bed_elevation_np)

    smb_rate = calculate_smb(ice_thickness_np, bed_elevation_np, sim_params)
    flow_rate = calculate_sia_flow_rate(ice_thickness_np, bed_elevation_np, sim_params)

    total_dhdt = smb_rate + flow_rate

    # Ensure rate is 0 in areas where bed elevation is NaN (no land/ice there)
    total_dhdt[np.isnan(bed_elevation_np)] = 0.0

    return total_dhdt


# --- Helper function to create the 3D Plotly figure ---
# This function must be defined AT THE TOP LEVEL (no indentation before def)
def create_3d_figure(ice_thickness_np, bed_elevation_np, X_grid_np, Y_grid_np, domain_bounds, current_year, total_years, sim_params):
    """Creates a Plotly 3D surface figure showing ice surface and bedrock."""

    ice_thickness_np = np.array(ice_thickness_np)
    bed_elevation_np = np.array(bed_elevation_np)

    minx, miny, maxx, maxy = domain_bounds

    surface_elevation_np = bed_elevation_np + ice_thickness_np
    surface_elevation_np[np.isnan(bed_elevation_np)] = np.nan

    finite_bed = bed_elevation_np[np.isfinite(bed_elevation_np)]
    finite_surf = surface_elevation_np[np.isfinite(surface_elevation_np)]

    min_elev_data = np.min(finite_bed) if finite_bed.size > 0 else 0
    max_elev_data = np.max(finite_surf) if finite_surf.size > 0 else (np.max(finite_bed) if finite_bed.size > 0 else 1000)

    elev_range = max_elev_data - min_elev_data
    if elev_range <= 100: elev_range = 200
    plot_z_min = min_elev_data - elev_range * 0.1
    plot_z_max = max_elev_data + elev_range * 0.2

    data = []

    bed_trace = go.Surface(
        x=X_grid_np, y=Y_grid_np, z=bed_elevation_np,
        colorscale='ylgnbu', # terrain is better than viridis for elevation
        cmin=np.nanmin(bed_elevation_np) if np.any(~np.isnan(bed_elevation_np)) else 0,
        cmax=np.nanmax(bed_elevation_np) if np.any(~np.isnan(bed_elevation_np)) else 1000,
        colorbar=dict(title='Bed Elev (m)'), showscale=True, name='Bedrock',
        contours = {"z": {"show": True, "size": 100, "color": "gray"}}
    )
    data.append(bed_trace)

    ice_surface_z_masked = np.copy(surface_elevation_np)
    ice_surface_z_masked[ice_thickness_np < MIN_THICKNESS_FOR_FLOW / 2.0] = np.nan
    ice_surface_z_masked[np.isnan(bed_elevation_np)] = np.nan

    if np.any(~np.isnan(ice_surface_z_masked)):
        ice_trace = go.Surface(
            x=X_grid_np, y=Y_grid_np, z=ice_surface_z_masked,
            colorscale='blues',
            cmin=plot_z_min + (plot_z_max - plot_z_min) * 0.1,
            cmax=plot_z_max,
            colorbar=dict(title='Ice Elev (m)'), showscale=True, name='Ice Surface',
            lighting=dict(ambient=0.8, diffuse=0.8, specular=0.2, roughness=0.5, fresnel=0.1),
            lightposition=dict(x= (minx+maxx)/2 + (maxx-minx), y= (miny+maxy)/2 + (maxy-miny), z= plot_z_max * 1.5)
        )
        data.append(ice_trace)

    fig = go.Figure(data=data)

    domain_dx = maxx - minx
    domain_dy = maxy - miny
    plot_z_range_aspect = plot_z_max - plot_z_min

    aspect_x = 1.0
    aspect_y = (domain_dy / domain_dx) if domain_dx > 0 else 1.0
    aspect_z = (plot_z_range_aspect / domain_dx * 0.5) if domain_dx > 0 and plot_z_range_aspect > 0 else 0.5

    if not np.isfinite(aspect_x) or aspect_x <= 0: aspect_x = 1.0
    if not np.isfinite(aspect_y) or aspect_y <= 0: aspect_y = 1.0
    if aspect_y > 5 or aspect_y < 0.2: aspect_y = max(0.5, min(2.0, aspect_y))
    if not np.isfinite(aspect_z) or aspect_z <= 0: aspect_z = 0.5
    if aspect_z > 5 or aspect_z < 0.01: aspect_z = max(0.05, min(2.0, aspect_z))


    fig.update_layout(
        title=f"Glacier Model (Year: {current_year:.0f} / {total_years:.0f})",
        scene=dict(
            xaxis_title='Easting (m)', yaxis_title='Northing (m)', zaxis_title='Elevation (m)',
            xaxis=dict(range=[minx, maxx]), yaxis=dict(range=[miny, maxy]), zaxis=dict(range=[plot_z_min, plot_z_max]),
            aspectmode='manual', aspectratio=dict(x=aspect_x, y=aspect_y, z=aspect_z), # Correctly use aspectRatio
            camera=dict(
                up=dict(x=0, y=0, z=1),
                center=dict(x= (minx+maxx)/2, y= (miny+maxy)/2, z=(plot_z_min+plot_z_max)/2),
                eye=dict(x=1.5, y=-1.5, z=1.0)
             )
        ),
        margin=dict(l=0, r=0, t=60, b=0),
        uirevision=f"year_{current_year:.0f}_params_{sim_params.get('temp_anomaly',0.0):.1f}_{sim_params.get('snowfall_rate',0.0):.1f}_{sim_params.get('flow_rate_factor',1e-15):.2e}", # Use .get safely
        plot_bgcolor='#f9f9f9', paper_bgcolor='#fff', height=700, hovermode='closest'
    )

    return fig


# --- Streamlit App Execution Flow (Main Script Body) ---
# This part must have ZERO indentation.

st.write("This application will simulate a glacier using a 2D grid based on real topography and physics.")
st.markdown("---")

# --- Sidebar: Parameters (Phase 2 Widgets) ---
st.sidebar.header("Model Parameters")

# Use forms to group parameters
with st.sidebar.form("climate_params_form"):
    st.subheader("Climate Settings")
    sim_temp_anomaly = st.number_input("Temperature Anomaly (°C)", min_value=-10.0, max_value=10.0, value=DEFAULT_TEMP_ANOMALY, step=0.1, format="%.1f", help="Temperature increase or decrease relative to a baseline.")
    sim_snowfall_rate = st.number_input("Snowfall Rate (m ice/year)", min_value=0.0, max_value=5.0, value=DEFAULT_SNOWFALL, step=0.05, format="%.2f", help="Rate of snow accumulation (ice equivalent).")
    sim_melt_factor = st.number_input("Melt Factor (m ice/yr per °C > freezing)", min_value=0.0001, max_value=0.02, value=DEFAULT_MELT_FACTOR, step=0.0001, format="%.4f", help="Sensitivity of melt to temperature above freezing.")
    sim_lapse_rate = st.number_input("Lapse Rate (°C/m)", min_value=0.003, max_value=0.01, value=DEFAULT_LAPSE_RATE, step=0.0001, format="%.4f", help="Rate at which temperature decreases with elevation.")
    sim_base_temp_above_freezing = st.number_input("Base Temp Above Freezing (°C at datum)", min_value=-10.0, max_value=15.0, value=DEFAULT_BASE_TEMP_ABOVE_FREEZING, step=0.1, format="%.1f", help="Avg temp difference above freezing at a low reference elevation.")
    submit_climate_params = st.form_submit_button("Apply Climate Parameters")

with st.sidebar.form("flow_params_form"):
    st.subheader("Flow Settings")
    sim_flow_rate_factor_exp = st.number_input(f"Flow Rate Factor (log10)", min_value=-20.0, max_value=-12.0, value=DEFAULT_FLOW_RATE_FACTOR_EXP, step=0.05, format="%.2f", help=f"Exponent of ice flow factor (log10). Higher value means faster flow.")
    actual_flow_rate_factor = 10**sim_flow_rate_factor_exp
    submit_flow_params = st.form_submit_button("Apply Flow Parameters")

st.sidebar.markdown("---")
st.sidebar.write(f"Model Grid Resolution: {GRID_RESOLUTION} m")
st.sidebar.write(f"Effective Flow Factor: {actual_flow_rate_factor:.2e}")

# --- Streamlit App Execution Flow (Continued) ---
st.markdown("---")

# --- Phase 1: Load and Process DEM into Model Grid (Cached) ---
# Check if DEM_PATH is still the default placeholder
if DEM_PATH == "path/to/your/1981Yala_dem_20_-10_bias_cor.tif":
    st.error("Please update the `DEM_PATH` variable at the top of the script with the actual file path to your 1981 Yala Glacier DEM.")
    st.stop()

# Define the actual bounding box tuple
BBOX_LONLAT = (BBOX_LON_MIN, BBOX_LAT_MIN, BBOX_LON_MAX, BBOX_LAT_MAX)

# Load and process the DEM
try:
    st.info("Loading and processing DEM (cached)...")
    processed_data = load_and_process_dem_cached(DEM_PATH, BBOX_LONLAT, GRID_RESOLUTION, UTM_CRS_EPSG)
    st.session_state['bed_elevation_np'] = processed_data[0]
    st.session_state['X_grid_np'] = processed_data[1]
    st.session_state['Y_grid_np'] = processed_data[2]
    st.session_state['domain_bounds'] = processed_data[3]
    # Ny and Nx are derived from the shape of bed_elevation_np
    Ny, Nx = st.session_state['bed_elevation_np'].shape

    st.success("DEM loaded and processed successfully.")

except Exception as e: # Catch exceptions originating from load_and_process_dem_cached
     st.error(f"Critical Error during DEM loading: {e}")
     # Use st.exception to show the full traceback in the app
     # st.exception(e) # It might already be shown by load_and_process_dem_cached's internal st.exception
     st.stop() # Stop if DEM loading fails

# --- Initialize/Reset Simulation State ---
# Determine if a reset is needed
reset_simulation = False
if 'ice_thickness_np' not in st.session_state or \
   st.session_state['bed_elevation_np'].shape != (Ny, Nx) or \
   submit_climate_params or submit_flow_params:
    reset_simulation = True

if reset_simulation:
    # Reset state to zero ice thickness, step 0, simulation stopped.
    st.session_state['ice_thickness_np'] = np.zeros((Ny, Nx))
    st.session_state['current_step'] = 0
    st.session_state['sim_running'] = False

    # Mask the initial ice thickness with NaN where the bed is NaN (off the land)
    st.session_state['ice_thickness_np'] = st.session_state['ice_thickness_np'].copy() # Work on a copy
    st.session_state['ice_thickness_np'][np.isnan(st.session_state['bed_elevation_np'])] = np.nan

    # Display info based on what triggered the reset
    if submit_climate_params or submit_flow_params:
         st.info("Simulation state reset due to parameter changes.")
    elif 'ice_thickness_np' not in st.session_state:
         st.info("Initial simulation state initialized (zero ice thickness).")
    # else: # Implies DEM loaded/changed and reset needed
    #      st.info("DEM dimensions changed, simulation state reset.")


# --- Pass current widget values to a parameter dictionary ---
# This dictionary is re-created on every rerun with the current widget values.
# It's used by the physics and plotting functions.
current_sim_params = {
    'time_step': DEFAULT_SIM_TIME_STEP, # Hardcoded for now (Phase 3 widget)
    'total_years': DEFAULT_TOTAL_YEARS, # Hardcoded for now (Phase 3 widget)
    'temp_anomaly': sim_temp_anomaly,
    'snowfall_rate': sim_snowfall_rate,
    'melt_factor': sim_melt_factor,
    'lapse_rate': sim_lapse_rate,
    'base_temp_above_freezing': sim_base_temp_above_freezing,
    'flow_rate_factor': actual_flow_rate_factor,
    'n_exponent': N_EXPONENT,
    'grid_resolution': GRID_RESOLUTION,
    'freezing_point': DEFAULT_FREEZING_POINT
}

# --- PHASE 3: Animation Loop Controls and Display (Placeholders) ---
st.markdown("---")
st.subheader("Simulation Controls")

# These buttons will control the simulation loop (Implemented in Phase 3)
col1, col2, col3 = st.columns(3)
with col1:
    # Start/Resume Button (Enabled/Disabled in Phase 3 logic)
    start_button = st.button('Start Simulation', disabled=True)

with col2:
    # Stop Button (Enabled/Disabled in Phase 3 logic)
    stop_button = st.button('Stop Simulation', disabled=True)

with col3:
     # Reset Button (Implemented in Phase 3 logic)
     reset_button = st.button('Reset Simulation', disabled=False) # Enabled manually now for visual


# --- Display Simulation Status (Updated in Phase 3) ---
current_year = st.session_state['current_step'] * current_sim_params['time_step']
total_years = current_sim_params['total_years']
status_text = f"Current Year: {current_year:.0f} / {total_years:.0f}"
if st.session_state.get('sim_running', False):
     status_text += " (Running)"
elif st.session_state['current_step'] > 0:
     status_text += " (Paused)"
else:
     status_text += " (Ready)" # Initial or after reset status

st.write(status_text)

# --- Plot Placeholder (Updated in Phase 3 animation loop) ---
plot_container = st.empty()


# --- PHASE 3: Simulation Animation Loop goes here ---
# The simulation loop will run here based on the 'sim_running' session state.
# It will call calculate_total_dhdt and update st.session_state['ice_thickness_np'].
# It will also call create_3d_figure and plot_container.plotly_chart in the loop.
# ... (While loop for simulation will be added here in Phase 3) ...


# --- Display the Plot (Initial/Static display or last state if not running) ---
# This block runs on every rerun when the animation loop is NOT active.
# It ensures the current state is displayed in the plot container.

# Ensure NumPy arrays for plotting functions
ice_thickness_plot = st.session_state['ice_thickness_np']
bed_elevation_plot = st.session_state['bed_elevation_np']
X_grid_plot = st.session_state['X_grid_np']
Y_grid_plot = st.session_state['Y_grid_np']
domain_bounds_plot = st.session_state['domain_bounds']

fig = create_3d_figure(
    ice_thickness_plot,
    bed_elevation_plot,
    X_grid_plot,
    Y_grid_plot,
    domain_bounds_plot,
    current_year,
    total_years,
    current_sim_params # Pass current parameters to the plotting function
)
plot_container.plotly_chart(fig, use_container_width=True)


st.markdown("---")
# Status message at the bottom, clarifies what this script stage does
st.info("Phase 2 Complete (Attempted). Physics functions and parameter widgets are defined.")
st.info("If you see the bedrock and a flat ice layer above it with widgets in the sidebar, it worked!")
st.info("Next Steps (Phase 3): Implement the simulation time loop, connect controls, and add volume calculation.")

# --- END OF SCRIPT ---