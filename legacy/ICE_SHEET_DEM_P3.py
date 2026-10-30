# glacier_model_2d_phase3_final.py

# --- Imports ---
import streamlit as st
import plotly.graph_objs as go
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject, Resampling # <--- Ensure THESE ARE HERE
import pyproj
import os
import time # Needed for animation pause
from rasterio.transform import Affine # For isinstance check


# --- Model Parameters (Constants and Defaults - defined at top level) ---
GRID_RESOLUTION = 100 # meters - Desired resolution for our model grid

# Geographic bounding box for Yala Glacier (Approximate)
# IMPORTANT: VERIFY these coordinates cover YOUR DEM file!
BBOX_LON_MIN = 85.570
BBOX_LAT_MIN = 28.200
BBOX_LON_MAX = 85.660
BBOX_LAT_MAX = 28.275

# PATH TO YOUR DEM FILE (Set correctly!)
# !!! ACTION REQUIRED: Replace this with the ACTUAL FULL PATH to your 1981 Yala Glacier DEM file !!!
DEM_PATH = "C:/Users/ALiEN/ICE_SHEET_DEM/DEM_and_ortho/DEM_and_ortho/1981Yala_dem_20_-10_bias_cor.tif" # <<< VERIFY THIS PATH IS CORRECT


# Projected Coordinate System (PCS) suitable for Langtang/Yala (UTM Zone 45N)
UTM_CRS_EPSG = 'EPSG:32645' # UTM Zone 45N


# --- Default/Initial Simulation Parameters (used for widget defaults) ---
DEFAULT_SIM_TIME_STEP = 10  # years
DEFAULT_TOTAL_YEARS = 100  # years

# Climate parameter defaults
DEFAULT_TEMP_ANOMALY = 0.0   # °C
DEFAULT_SNOWFALL = 0.5       # m ice eq. / year
DEFAULT_MELT_FACTOR = 0.003  # m ice eq. / year / °C above freezing
DEFAULT_LAPSE_RATE = 0.0065  # °C per meter
# Simplified Temp Model base (effectively controls freezing level + datum temp)
DEFAULT_BASE_TEMP_ABOVE_FREEZING = 5.0 # °C
DEFAULT_FREEZING_POINT = 0.0 # °C (Reference value, not used directly in simplified melt calc)


# Ice Flow parameters defaults
DEFAULT_FLOW_RATE_FACTOR_EXP = -15.0 # Exponent for Flow Rate Factor ~ 10^-15
MIN_THICKNESS_FOR_FLOW = 0.1 # meters - ice must be this thick to flow significantly

# Glen's Flow Law exponent for ice (used in SIA flux)
N_EXPONENT = 3.0

# Animation Speed Control
ANIMATION_DELAY_SECONDS = 0.01 # Smaller means faster animation update


# --- Helper function for DEM Loading and Processing (Cached) ---
# Must be defined at top level
@st.cache_resource
def load_and_process_dem_cached(dem_path, bbox_lonlat, grid_resolution, target_crs_epsg):
    """
    Loads DEM, clips to bbox, reprojects, and resamples.
    Returns bed elevation, X/Y coords, domain bounds, transform.
    """
    st.info(f"Attempting to load DEM from {os.path.basename(dem_path)}...")
    if not os.path.exists(dem_path): st.error(f"Error: DEM file not found: {dem_path}"); st.stop()
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
            if minx >= maxx or miny >= maxy: st.error(f"Error: Transformed BBOX coords result in invalid range: [{minx:.0f},{maxx:.0f}]m, [{miny:.0f},{maxy:.0f}]m. Check BBOX order/values."); st.stop()

            # --- Define Target Grid ---
            grid_width = maxx - minx; grid_height = maxy - miny
            nx = int(np.ceil(grid_width / grid_resolution)); ny = int(np.ceil(grid_height / grid_resolution))
            if nx < 2 or ny < 2: st.error(f"Error: Calculated grid size {nx}x{ny} too small (< 2x2). Adjust BBOX/GRID_RESOLUTION."); st.stop()
            bed_elevation = np.empty((ny, nx), dtype=np.float32)

            # --- Define Target Transform ---
            try: target_transform = rasterio.transform.from_bounds(minx, miny, maxx, maxy, nx, ny);
            except Exception as e: st.error(f"Error creating target transform: {e}"); st.stop()

            # --- Reproject and Resample ---
            st.info("Attempting rasterio.warp.reproject...")
            try:
                reproject(source=rasterio.band(src, 1), destination=bed_elevation,
                    src_transform=src.transform, src_crs=src.crs,
                    dst_transform=target_transform, dst_crs=target_crs_epsg,
                    resampling=Resampling.bilinear, num_threads=os.cpu_count() or 1)
                st.success("Rasterio reprojection successful.")
            except Exception as e: st.error(f"--- ERROR during rasterio.warp.reproject ---"); st.exception(e); st.info("Debug Info: Check Transforms/CRSs. Source: {src.crs}/{src.transform}, Target: {target_crs_epsg}/{target_transform}."); st.stop()

            # --- Handle NoData ---
            nodata = src.nodata
            if nodata is not None and np.isfinite(nodata) and np.any(np.isfinite(bed_elevation)):
                 nodata_mask = np.isclose(bed_elevation, nodata) if bed_elevation.dtype.kind == 'f' else (bed_elevation == nodata)
                 if np.any(nodata_mask): bed_elevation[nodata_mask] = np.nan; st.info(f"Replaced {np.sum(nodata_mask)} values matching NoData ({nodata}) with NaN.")

            # --- Generate Grid Coordinates ---
            cols, rows = np.meshgrid(np.arange(nx), np.arange(ny))
            X_grid, Y_grid = target_transform * (cols.flatten() + 0.5, rows.flatten() + 0.5)
            X_grid = X_grid.reshape((ny, nx)); Y_grid = Y_grid.reshape((ny, nx))

            # --- Final Checks ---
            if bed_elevation.shape != (ny, nx) or X_grid.shape != (ny, nx) or Y_grid.shape != (ny, nx): st.error("Internal Error: Generated arrays have incorrect shape."); st.stop()
            if not np.any(np.isfinite(bed_elevation)): st.warning("Warning: Loaded DEM region contains no finite elevation data.");

            return bed_elevation, X_grid, Y_grid, (minx, miny, maxx, maxy), target_transform

    except Exception as e: st.error(f"An unexpected error during DEM loading/processing (before reproject):"); st.exception(e); st.stop()


# --- Helper functions for Physics (defined at top level) ---
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
        # Using BaseTempAboveFreezing + Anomaly - LapseRate*Elev
        temp_above_freezing_valid = (sim_params['base_temp_above_freezing'] + sim_params['temp_anomaly']) - sim_params['lapse_rate'] * valid_surf_elev
        melt_rate_valid = sim_params['melt_factor'] * np.maximum(0.0, temp_above_freezing_valid)
        smb_valid = accumulation_rate_valid - melt_rate_valid
        smb[valid_mask] = smb_valid
    return smb

# Replace the calculate_sia_flow_rate function in your script with this version.

def calculate_sia_flow_rate(ice_thickness_np, bed_elevation_np, sim_params):
    """
    Calculates the rate of thickness change due to ice flow (SIA).
    dH/dt = -nabla dot q. Units: meters / year
    Corrected logic for gradient masking.
    """
    ice_thickness_np = np.array(ice_thickness_np)
    bed_elevation_np = np.array(bed_elevation_np)
    Ny, Nx = ice_thickness_np.shape
    surface_elevation_np = bed_elevation_np + ice_thickness_np
    surface_elevation_np[np.isnan(bed_elevation_np)] = np.nan # Propagate NaN from bed


    # Calculate gradients of surface elevation using central differences
    # np.gradient handles boundary conditions ('edge' default) and propagates NaNs.
    # Returns dy then dx
    dSdy, dSdx = np.gradient(surface_elevation_np, sim_params['grid_resolution'])

    # --- Implement SIA Flux (Simplified) ---
    # q = - C * H^(n+2) * grad(S), where n=3, so H^5
    # C captures the flow_rate_factor.
    # Flux should be zero where ice thickness H is zero or effectively zero (< MIN_THICKNESS_FOR_FLOW).
    # Also zero where bedrock is NaN.

    H_eff = np.maximum(0.0, ice_thickness_np) # Use max(0, H) for exponentiation

    # Mask out areas where ice is too thin to flow significantly or where bedrock is NaN
    # This mask will be used to assign *calculated* flux values back into the full array.
    can_flow_mask = (H_eff >= MIN_THICKNESS_FOR_FLOW) & (~np.isnan(bed_elevation_np))

    # Initialize flux components over the FULL grid to zero
    q_x = np.zeros_like(ice_thickness_np)
    q_y = np.zeros_like(ice_thickness_np)

    # Calculate flux components *only* at the locations where flow is possible
    if np.any(can_flow_mask):
        # Get H and gradient components *only* for locations within the can_flow_mask
        # Note: If dSdx or dSdy were NaN in the full grid, they will also be NaN here.
        # If bed_elevation_np is NaN, can_flow_mask is False, so we don't need to worry about NaNs *from* bed.
        dSdx_masked = dSdx[can_flow_mask]
        dSdy_masked = dSdy[can_flow_mask]
        H_masked = H_eff[can_flow_mask]

        # --- Corrected Flux Calculation ---
        # Calculate the flux components *over the subset selected by can_flow_mask*.
        # This calculation will result in NaNs where the gradients (dSdx_masked/dSdy_masked) are NaN.
        # The shape of the results (q_x_calc, q_y_calc) will match the number of True values in can_flow_mask.
        q_x_calc = - sim_params['flow_rate_factor'] * (H_masked**(N_EXPONENT + 2)) * dSdx_masked
        q_y_calc = - sim_params['flow_rate_factor'] * (H_masked**(N_EXPONENT + 2)) * dSdy_masked

        # --- Assign the calculated flux values back to the corresponding locations in the full q_x, q_y arrays ---
        # The shape of q_x_calc/q_y_calc now matches the shape of the can_flow_mask subset.
        q_x[can_flow_mask] = q_x_calc
        q_y[can_flow_mask] = q_y_calc


    # --- Calculate Divergence of Flux ---
    # Divergence (nabla dot q) = d(q_x)/dx + d(q_y)/dy
    # We need gradients of q_x and q_y. Set any NaNs in q_x, q_y to 0 for the gradient calculation
    # part of divergence, as np.gradient treats NaNs in input as boundary conditions or propagates.
    # Replacing NaNs with 0 ensures d(q)/d(coord) = 0 where flow isn't happening or gradient was NaN.
    q_x_for_div = np.nan_to_num(q_x, nan=0.0)
    q_y_for_div = np.nan_to_num(q_y, nan=0.0)

    # Use the actual grid resolution for gradient spacing
    # np.gradient returns dy then dx
    dqx_dx, dqx_dy = np.gradient(q_x_for_div, sim_params['grid_resolution'])
    dqy_dx, dqy_dy = np.gradient(q_y_for_div, sim_params['grid_resolution'])

    # Divergence = dqx/dx + dqy/dy
    # Sum corresponding gradient components
    divergence_q = dqx_dx + dqy_dy


    # Change in thickness due to flow is - Divergence(q)
    dhdt_flow = -divergence_q

    # Ensure dhdt_flow is 0 in areas where bed is NaN (no land/ice there)
    # Although calculating divergence of 0 flux (after nan_to_num) over NaNs should be 0 anyway,
    # explicitly setting to 0 ensures this.
    dhdt_flow[np.isnan(bed_elevation_np)] = 0.0 # Set explicitly to 0

    # Note: NaNs in dH/dt can still arise if bedrock isn't NaN but gradients become massive/infinite
    # leading to Inf flux values before nan_to_num. np.nan_to_num replaces Infs with very large finite numbers.
    # If simulations become unstable (Inf/NaN thicknesses), check step size and parameters.

    return dhdt_flow # Units: meters / year

def calculate_total_dhdt(ice_thickness_np, bed_elevation_np, sim_params):
    """
    Calculates the total rate of thickness change (dH/dt = SMB + Flow_term).
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

# --- Optional: Calculate total ice volume (defined at top level) ---
def calculate_volume(ice_thickness_np, grid_resolution, bed_elevation_np):
    """Calculates the total volume of ice."""
    # Only sum volume where ice thickness > 0 and bedrock is not NaN
    # Ensure bedrock_np is checked for NaNs as well
    volume = np.sum(ice_thickness_np[(ice_thickness_np > 0) & (~np.isnan(bed_elevation_np))]) * (grid_resolution**2)
    return volume # Units: cubic meters

# --- Helper function to create the 3D Plotly figure (defined at top level) ---
def create_3d_figure(ice_thickness_np, bed_elevation_np, X_grid_np, Y_grid_np, domain_bounds, current_year, total_years, sim_params):
    """Creates a Plotly 3D surface figure showing ice surface and bedrock."""

    ice_thickness_np = np.array(ice_thickness_np)
    bed_elevation_np = np.array(bed_elevation_np)
    minx, miny, maxx, maxy = domain_bounds

    surface_elevation_np = bed_elevation_np + ice_thickness_np
    surface_elevation_np[np.isnan(bed_elevation_np)] = np.nan # Propagate NaN from bed

    # Calculate min/max elevations for color scaling and Z axis range, ignoring NaNs
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
    # Mask very thin ice for display
    ice_surface_z_masked[ice_thickness_np < MIN_THICKNESS_FOR_FLOW / 2.0] = np.nan
    # Mask where bedrock is NaN (already done by surface_elevation_np but double check)
    ice_surface_z_masked[np.isnan(bed_elevation_np)] = np.nan


    if np.any(~np.isnan(ice_surface_z_masked)):
        ice_trace = go.Surface(
            x=X_grid_np, y=Y_grid_np, z=ice_surface_z_masked,
            colorscale='blues', # Use a blue scale
            cmin=plot_z_min + (plot_z_max - plot_z_min) * 0.1,
            cmax=plot_z_max,
            colorbar=dict(title='Ice Elev (m)'), showscale=True, name='Ice Surface',
            lighting=dict(ambient=0.8, diffuse=0.8, specular=0.2, roughness=0.5, fresnel=0.1),
            # Light position relative to the center/size of the domain
            lightposition=dict(
                x= -10, # Example: Light from the left/West
                y= -10, # Example: Light from the bottom/South
                z= 20   # Example: Light from above
            )
        )
        data.append(ice_trace)

    fig = go.Figure(data=data)

    # Aspect ratio calculation
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
            aspectmode='manual', # Correctly use aspectmode='manual'
            aspectratio=dict(x=aspect_x, y=aspect_y, z=aspect_z), # Correctly use aspectRatio

            camera=dict( # Initial camera position
                up=dict(x=0, y=0, z=1),
                center=dict(x= (minx+maxx)/2, y= (miny+maxy)/2, z=(plot_z_min+plot_z_max)/2), # Center camera
                eye=dict(x=1.5, y=-1.5, z=1.0) # Relative eye position
            )
        ),
        margin=dict(l=0, r=0, t=60, b=0),
        # Update uirevision based on year and parameters
        # Using .get() with defaults to safely access sim_params keys
        uirevision=f"year_{current_year:.0f}_params_{sim_params.get('temp_anomaly',0.0):.1f}_{sim_params.get('snowfall_rate',0.0):.1f}_{sim_params.get('flow_rate_factor',1e-15):.2e}",
        plot_bgcolor='#f9f9f9', paper_bgcolor='#fff', height=700, hovermode='closest'
    )

    return fig


# --- Streamlit App Execution Flow (Main Script Body - NO INDENTATION) ---
# This is the main part of the script that gets executed top-to-bottom on every rerun.

# Set page configuration for wider layout
st.set_page_config(layout="wide")


st.write("This application will simulate a glacier using a 2D grid based on real topography and physics.")
st.markdown("---")

# --- Sidebar: Parameters (Phase 2/3 Widgets) ---
# These widgets define the model parameters and live in the sidebar.
st.sidebar.header("Model Parameters")

# Use forms to group parameters. Changes require form submit to trigger a rerun with new values.
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
    actual_flow_rate_factor = 10**sim_flow_rate_factor_exp # Calculate actual value
    submit_flow_params = st.form_submit_button("Apply Flow Parameters")

# Time/Years Widgets (Phase 3)
with st.sidebar.form("time_params_form"):
     st.subheader("Simulation Time")
     sim_time_step = st.number_input("Simulation Time Step (years)", min_value=1, max_value=1000, value=DEFAULT_SIM_TIME_STEP, step=1, help="Length of each simulation step in years.")
     sim_total_years = st.number_input("Total Simulation Years", min_value=100, max_value=500000, value=DEFAULT_TOTAL_YEARS, step=100, help="Total simulated duration.")
     submit_time_params = st.form_submit_button("Apply Time Parameters")

st.sidebar.markdown("---")
st.sidebar.write(f"Model Grid Resolution: {GRID_RESOLUTION} m")
st.sidebar.write(f"Effective Flow Factor: {actual_flow_rate_factor:.2e}")

# Derived parameter (calculate nSteps) - Use current widget values
nSteps = int(sim_total_years / sim_time_step) if sim_time_step > 0 else 0
if nSteps == 0 and sim_total_years > 0:
    st.warning("Simulation duration is less than time step. Using nSteps=1.")
    nSteps = 1
st.sidebar.write(f"Derived Number of Steps: {nSteps}") # Display nSteps in sidebar


# --- Streamlit App Execution Flow (Continued) ---
st.markdown("---")

# --- Phase 1: Load and Process DEM into Model Grid (Cached) ---
# Check if DEM_PATH is still the default placeholder
if DEM_PATH == "path/to/your/1981Yala_dem_20_-10_bias_cor.tif":
    st.error("Please update the `DEM_PATH` variable at the top of the script.")
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
    Ny, Nx = st.session_state['bed_elevation_np'].shape

    st.success("DEM loaded and processed successfully.")

except Exception as e: # Catch exceptions originating from load_and_process_dem_cached
     st.error(f"Critical Error during DEM loading: {e}")
     # st.exception(e) # load_and_process_dem_cached already shows exception details
     st.stop() # Stop if DEM loading fails


# --- Initialize/Reset Simulation State (Phase 2/3 Logic) ---
# Determine if a reset is needed:
# - Initial load (no ice_thickness_np in session state)
# - Bedrock shape changed (different DEM/BBOX leads to different Ny, Nx)
# - Any parameter form (Climate, Flow, Time) was submitted
reset_simulation = False
if 'ice_thickness_np' not in st.session_state or \
   st.session_state['bed_elevation_np'].shape != (Ny, Nx) or \
   submit_climate_params or submit_flow_params or submit_time_params:
    reset_simulation = True

if reset_simulation:
    # Reset state to zero ice thickness, step 0, simulation stopped.
    st.session_state['ice_thickness_np'] = np.zeros((Ny, Nx))
    st.session_state['current_step'] = 0
    st.session_state['sim_running'] = False

    # Mask initial ice thickness with NaN where bed is NaN
    # Use .copy() to ensure a new array is created, not just a view/reference
    st.session_state['ice_thickness_np'] = st.session_state['ice_thickness_np'].copy()
    st.session_state['ice_thickness_np'][np.isnan(st.session_state['bed_elevation_np'])] = np.nan

    # Display info based on what triggered the reset
    if submit_climate_params or submit_flow_params or submit_time_params:
         st.info("Simulation state reset due to parameter changes.")
    elif 'ice_thickness_np' not in st.session_state:
         st.info("Initial simulation state initialized (zero ice thickness).")
    # else: # Implies DEM loaded/changed and reset needed
    #      st.info("DEM dimensions changed, simulation state reset.")


# --- Pass current widget values to a parameter dictionary ---
# This dictionary is re-created on every rerun with the current widget values.
# It's used by the physics and plotting functions.
current_sim_params = {
    'time_step': sim_time_step, # Use widget value
    'total_years': sim_total_years, # Use widget value
    'temp_anomaly': sim_temp_anomaly,
    'snowfall_rate': sim_snowfall_rate,
    'melt_factor': sim_melt_factor,
    'lapse_rate': sim_lapse_rate,
    'base_temp_above_freezing': sim_base_temp_above_freezing,
    'flow_rate_factor': actual_flow_rate_factor, # Use the actual value from the calculation
    'n_exponent': N_EXPONENT,
    'grid_resolution': GRID_RESOLUTION,
    'freezing_point': DEFAULT_FREEZING_POINT # Included for completeness, from global constant
}


# --- PHASE 3: Animation Loop Controls and Display ---
st.markdown("---")
st.subheader("Simulation Controls")

# These buttons will control the simulation loop
col1, col2, col3 = st.columns(3)

with col1:
    # Start/Resume Button
    # Disabled if already running OR simulation is complete (current step >= nSteps)
    start_button = st.button('Start Simulation', disabled=st.session_state.get('sim_running', False) or st.session_state['current_step'] >= nSteps)

with col2:
    # Stop Button
    # Disabled if simulation is NOT running or is at the beginning (step 0)
    stop_button = st.button('Stop Simulation', disabled=not st.session_state.get('sim_running', False) or st.session_state['current_step'] == 0)

with col3:
     # Reset Button
     # Enabled if simulation is running or has progressed (> step 0)
     reset_button = st.button('Reset Simulation', disabled=st.session_state['current_step'] == 0 and not st.session_state.get('sim_running', False))


# Handle button clicks to update 'sim_running' state
# The 'submit' buttons from forms already cause reset logic to run above.
# These buttons control only the *running* state and potentially trigger a rerun.
if start_button:
    if st.session_state['current_step'] < nSteps:
         st.session_state['sim_running'] = True
         # info message handled below before loop
         # Trigger rerun if button pressed
         st.rerun()

if stop_button:
    st.session_state['sim_running'] = False
    st.info("Simulation paused.")
    # No rerun needed, stopping causes exit from while loop below


# Handle manual Reset button click
if reset_button:
     # Reset logic is primarily handled above when `reset_simulation` becomes True.
     # The button click itself triggers a rerun where `reset_simulation` is evaluated.
     # Ensure the state flags are correct on reset
     st.session_state['sim_running'] = False
     st.session_state['current_step'] = 0 # Explicitly reset step
     # The actual ice thickness reset is handled above
     st.info("Manual Reset requested. Simulation state will reset on next rerun.")
     # Trigger rerun if button pressed to apply reset logic immediately
     st.rerun()


# --- Display Simulation Status ---
current_year = st.session_state['current_step'] * current_sim_params['time_step']
total_years = current_sim_params['total_years']
status_text = f"Current Year: {current_year:.0f} / {total_years:.0f} years (Step {st.session_state['current_step']}/{nSteps})"

# Determine dynamic status part
if st.session_state.get('sim_running', False):
    status_text += " (Running)"
elif st.session_state['current_step'] >= nSteps:
    status_text = f"Simulation Finished (Year: {total_years:.0f} / {total_years:.0f}) (Step {st.session_state['current_step']}/{nSteps})"
    st.session_state['sim_running'] = False # Ensure flag is false if finished
elif st.session_state['current_step'] > 0:
    status_text += " (Paused)"
else:
    status_text += " (Ready)" # Initial or after reset status

# Use a placeholder to update the status text dynamically
status_placeholder = st.empty()
status_placeholder.write(status_text)


# --- Optional: Display Total Ice Volume ---
# Create a placeholder in the sidebar for dynamic volume display
volume_placeholder = st.sidebar.empty()
current_volume = calculate_volume(
    st.session_state['ice_thickness_np'],
    current_sim_params['grid_resolution'],
    st.session_state['bed_elevation_np']
)
volume_placeholder.write(f"Total Ice Volume: {current_volume:.2e} m³")


# --- Plot Placeholder ---
# Create an empty container where the plot will be drawn and updated.
plot_container = st.empty()


# --- PHASE 3: Simulation Animation Loop ---
# This loop runs multiple simulation steps within a single Streamlit rerun *if*
# the condition is met when the script is executed top-to-bottom.

# Only enter the loop if 'sim_running' is True AND we haven't reached the end step
if st.session_state.get('sim_running', False) and st.session_state['current_step'] < nSteps:

    # The while loop continues until the 'sim_running' flag becomes False
    # or the total steps are reached. Each iteration is a Streamlit micro-rerun.
    while st.session_state.get('sim_running', False) and st.session_state['current_step'] < nSteps:

        # --- Perform Simulation Step ---
        # Calculate the rate of change (dH/dt) for the current state using physics functions
        dHdt = calculate_total_dhdt(
            st.session_state['ice_thickness_np'],
            st.session_state['bed_elevation_np'],
            current_sim_params # Pass current parameters from widgets
        )

        # Update ice thickness using Forward Euler explicit time step
        st.session_state['ice_thickness_np'] += dHdt * current_sim_params['time_step']

        # --- Enforce Physical Constraints ---
        # Ice thickness cannot be negative
        st.session_state['ice_thickness_np'] = np.maximum(0.0, st.session_state['ice_thickness_np'])
        # Ensure thickness is NaN where bed is NaN (handles ice flowing off the land)
        st.session_state['ice_thickness_np'][np.isnan(st.session_state['bed_elevation_np'])] = np.nan


        # --- Update Simulation State ---
        st.session_state['current_step'] += 1
        current_year = st.session_state['current_step'] * current_sim_params['time_step']

        # --- Update Display ---
        # Create the figure for the updated state
        fig = create_3d_figure(
            st.session_state['ice_thickness_np'],
            st.session_state['bed_elevation_np'],
            st.session_state['X_grid_np'],
            st.session_state['Y_grid_np'],
            st.session_state['domain_bounds'],
            current_year,
            total_years, # Use widget value for total years display
            current_sim_params # Pass params for plot Uirevision
        )

        # Update the plot in the container
        plot_container.plotly_chart(fig, use_container_width=True)

        # Update the status text (using the placeholder)
        status_text = f"Current Year: {current_year:.0f} / {total_years:.0f} years (Step {st.session_state['current_step']}/{nSteps}) (Running)"
        status_placeholder.write(status_text)

        # Update volume display in sidebar
        current_volume = calculate_volume(
             st.session_state['ice_thickness_np'],
             current_sim_params['grid_resolution'],
             st.session_state['bed_elevation_np']
        )
        volume_placeholder.write(f"Total Ice Volume: {current_volume:.2e} m³")


        # --- Control Animation Speed ---
        time.sleep(ANIMATION_DELAY_SECONDS) # Pause

        # Streamlit will automatically trigger reruns here,
        # allowing the script to re-evaluate the while loop condition.

    # --- After the while loop exits (either stopped or finished) ---
    # The script continues executing top-to-bottom.

    # If the loop exited because simulation finished, update status one last time
    if st.session_state['current_step'] >= nSteps:
         st.session_state['sim_running'] = False # Ensure flag is false
         # Final status message is written below the loop.
         # Volume updated in the last iteration.


# --- Display the Plot when simulation is NOT running ---
# This block runs on initial load, after pause, reset, or simulation finished.
# It ensures the current state in session_state is always rendered in the plot container.
else:
    # Use data directly from session state (which is the latest state)
    ice_thickness_plot = st.session_state['ice_thickness_np']
    bed_elevation_plot = st.session_state['bed_elevation_np']
    X_grid_plot = st.session_state['X_grid_np']
    Y_grid_plot = st.session_state['Y_grid_np']
    domain_bounds_plot = st.session_state['domain_bounds']

    # Display the plot using the current state
    fig = create_3d_figure(
        ice_thickness_plot,
        bed_elevation_plot,
        X_grid_plot,
        Y_grid_plot,
        domain_bounds_plot,
        current_year, # Current year from state
        total_years, # Total years from current parameters
        current_sim_params # Pass params
    )
    plot_container.plotly_chart(fig, use_container_width=True)

    # Status text is updated above the loop section. Volume updated there as well.


# --- Final Status/Info Messages at the bottom ---
st.markdown("---")
if st.session_state['current_step'] >= nSteps:
     st.success(f"Simulation completed after {total_years:.0f} years.")
elif not st.session_state.get('sim_running', False) and st.session_state['current_step'] > 0:
     st.info(f"Simulation paused at Year {current_year:.0f}.")
elif not st.session_state.get('sim_running', False) and st.session_state['current_step'] == 0:
      st.info("Simulation is ready. Adjust parameters in the sidebar and click 'Start Simulation'.")


# --- END OF SCRIPT ---