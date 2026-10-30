# glacier_model_2d_phase1_debug.py (Based on phase1 code, added debug)

import streamlit as st
import plotly.graph_objs as go
import numpy as np
import rasterio
# from rasterio.windows import from_bounds # Not directly used in this simplified read
# from rasterio.transform import Affine # Not directly used in this simplified read
import pyproj
import os
# import time # Not needed in Phase 1 debug

# --- Model Parameters (Fixed for grid and DEM input) ---
GRID_RESOLUTION = 100 # meters - Desired resolution for our model grid

# Geographic bounding box for Yala Glacier, Langtang Valley, Nepal (Approximate)
BBOX_LON_MIN = 85.570
BBOX_LAT_MIN = 28.200
BBOX_LON_MAX = 85.660
BBOX_LAT_MAX = 28.275

# Path to your DEM file (GeoTIFF format, e.g., .tif)
# !!! ACTION REQUIRED: Replace this with the ACTUAL FULL PATH to your 1981 Yala Glacier DEM file !!!
DEM_PATH = "C:/Users/ALiEN/ICE_SHEET_DEM/DEM_and_ortho/DEM_and_ortho/1981Yala_dem_20_-10_bias_cor.tif" # <<< SET YOUR ACTUAL FILE PATH HERE


# Projected Coordinate System (PCS) suitable for Langtang/Yala (UTM Zone 45N)
UTM_CRS_EPSG = 'EPSG:32645' # UTM Zone 45N


# --- Streamlit App Title ---
st.title("2D Glacier Model: Phase 1 Debugging DEM Load") # Updated title


# --- Sidebar: Parameters Placeholder ---
st.sidebar.header("Model Parameters")
st.sidebar.info("Parameter widgets will be added here in later phases (e.g., Climate, Flow).")
st.sidebar.markdown("---")
st.sidebar.write(f"Model Grid Resolution: {GRID_RESOLUTION} m")


# --- Load and Process DEM into Model Grid (Cached) ---
# This function is cached by Streamlit. It runs only once for a given set of inputs.
@st.cache_resource # Use cache_resource for larger objects like arrays
def load_and_process_dem_cached(dem_path, bbox_lonlat, grid_resolution, target_crs_epsg):
    """
    Loads DEM, clips to bbox, reprojects to target_crs, and resamples to grid_resolution.
    Returns bed elevation (np array), X/Y grid coordinates (np arrays),
    domain bounds in target CRS, and target transform.
    Includes debug steps.
    """

    st.info(f"Attempting to load DEM from {os.path.basename(dem_path)}...")

    if not os.path.exists(dem_path):
        st.error(f"Error: DEM file not found at: {dem_path}")
        st.info("Please check the DEM_PATH variable in the script and ensure the file exists.")
        st.stop()

    lon_min, lat_min, lon_max, lat_max = bbox_lonlat
    bbox_wgs84 = (lon_min, lat_min, lon_max, lat_max) # Keep as tuple


    try:
        with rasterio.open(dem_path) as src:
            st.write(f"DEM opened successfully.")
            st.write(f"Source CRS: {src.crs}")
            st.write(f"Source Transform: {src.transform}") # Added debug output
            st.write(f"Source Bounds: {src.bounds}")     # Added debug output
            st.write(f"Source NoData value: {src.nodata}")

            if src.crs is None:
                 st.error("Error: Source DEM has no CRS defined.")
                 st.stop()
            if src.transform is None:
                 st.error("Error: Source DEM has no Transform defined.")
                 st.stop()


            # Use pyproj to define transformers for reprojection
            st.write(f"Target CRS (EPSG): {target_crs_epsg}")
            try:
                 transformer_wgs84_to_target = pyproj.Transformer.from_crs("EPSG:4326", target_crs_epsg, always_xy=True)
                 st.write("Pyproj transformer created successfully.")
            except Exception as e:
                 st.error(f"Error creating pyproj transformer: {e}")
                 st.info("Ensure pyproj and its data are installed correctly (conda install pyproj).")
                 st.stop()


            # Define target grid extent in the target CRS (UTM) by transforming the bbox corners
            st.write(f"Input WGS84 Bbox: {bbox_wgs84}")
            try:
                minx, miny = transformer_wgs84_to_target.transform(lon_min, lat_min)
                maxx, maxy = transformer_wgs84_to_target.transform(lon_max, lat_max)
                target_bounds_utm = rasterio.coords.BoundingBox(minx, miny, maxx, maxy)
                st.write(f"Target Bounds in {target_crs_epsg}: {target_bounds_utm}")
            except Exception as e:
                 st.error(f"Error transforming bounding box coordinates: {e}")
                 st.stop()


            grid_width = maxx - minx
            grid_height = maxy - miny

            if grid_width <= 0 or grid_height <= 0:
                 st.error(f"Error: Calculated target grid width ({grid_width}) or height ({grid_height}) is not positive. Check BBOX_LON_MIN/MAX, BBOX_LAT_MIN/MAX.")
                 st.stop()

            nx = int(np.ceil(grid_width / grid_resolution))
            ny = int(np.ceil(grid_height / grid_resolution))

            if nx < 2 or ny < 2:
                st.error(f"Error: Calculated grid size {nx}x{ny} is too small (< 2x2). Adjust BBOX or GRID_RESOLUTION.")
                st.stop()

            st.write(f"Calculated target grid size: {nx} columns x {ny} rows")
            st.write(f"Target grid resolution: {grid_resolution} m")


            # Create an empty array for the resampled bed elevation in target CRS
            bed_elevation = np.empty((ny, nx), dtype=src.dtypes[0])

            # Define the affine transform for the target grid
            from rasterio.transform import from_bounds # Import inside function if needed
            target_transform = from_bounds(minx, miny, maxx, maxy, nx, ny)
            st.write(f"Target Transform created: {target_transform}") # Added debug output


            # --- This is the line that caused the previous error ---
            st.info("Attempting rasterio.warp.reproject...")
            from rasterio.warp import reproject, Resampling
            try:
                reproject(
                    source=rasterio.band(src, 1), # Read band 1
                    destination=bed_elevation,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=target_transform,
                    dst_crs=target_crs_epsg,
                    resampling=Resampling.bilinear,
                    num_threads=os.cpu_count() or 1
                )
                st.success("Reprojection successful.") # Added success message
            except Exception as e: # Catch specific exceptions or a broader Exception for debugging
                 st.error(f"Error during reprojection/resampling: {e}")
                 st.info("Troubleshooting tips: Ensure rasterio and GDAL are installed correctly. Check if the DEM file is valid and covers the chosen bounding box.")
                 # Re-raising the exception here might provide a more detailed traceback in the terminal
                 # raise e
                 st.stop() # Stop execution


            # Handle NoData values (replace with NaN)
            nodata = src.nodata
            if nodata is not None:
                 original_nodata_count = np.sum(bed_elevation == nodata)
                 bed_elevation[bed_elevation == nodata] = np.nan
                 st.info(f"Replaced {original_nodata_count} NoData values ({nodata}) with NaN.")
            else:
                 st.info("No explicit NoData value found in DEM metadata.")

            st.write(f"Bed elevation array created (shape: {bed_elevation.shape}, dtype: {bed_elevation.dtype}).")


            # Generate X and Y coordinates for the centers of the target grid cells
            x_coords = np.linspace(minx + grid_resolution/2, maxx - grid_resolution/2, nx)
            y_coords = np.linspace(miny + grid_resolution/2, maxy - grid_resolution/2, ny)
            X_grid, Y_grid = np.meshgrid(x_coords, y_coords)

            st.write(f"Generated X_grid and Y_grid coordinates.")

            return bed_elevation, X_grid, Y_grid, (minx, miny, maxx, maxy), target_transform

    except Exception as e:
        # Catch any other unexpected errors during processing outside the explicit try/except blocks
        st.error(f"An unexpected error occurred during DEM loading or processing: {e}")
        st.stop()


# --- Helper function to create the 3D Plotly figure (Phase 1: Just Bedrock) ---
def create_bedrock_figure(bed_elevation_np, X_grid_np, Y_grid_np, domain_bounds):
    """Creates a Plotly 3D surface figure showing ONLY the bedrock topography."""

    minx, miny, maxx, maxy = domain_bounds
    # Calculate realistic Z range from the data, handling possible NaNs
    # Use finite values only
    finite_bed_elevations = bed_elevation_np[np.isfinite(bed_elevation_np)]
    if finite_bed_elevations.size > 0:
         bed_min = np.min(finite_bed_elevations)
         bed_max = np.max(finite_bed_elevations)
    else: # Fallback if data is all NaN
         bed_min = 0
         bed_max = 1000 # Fallback


    # Add padding to the Z range for better visualization
    bed_range = bed_max - bed_min
    if bed_range == 0: bed_range = 100 # Avoid division by zero if area is flat
    plot_z_min = bed_min - bed_range * 0.1
    plot_z_max = bed_max + bed_range * 0.2


    # Bedrock surface trace
    bed_trace = go.Surface(
        x=X_grid_np, # Easting
        y=Y_grid_np, # Northing
        z=bed_elevation_np, # Elevation (NaNs handled by Plotly)
        colorscale='viridis', # Use a terrain color scale
        cmin=bed_min, # Color scale min based on data
        cmax=bed_max, # Color scale max based on data
        colorbar=dict(title='Bed Elevation (m)'),
        showscale=True,
        name='Bedrock'
    )

    fig = go.Figure(data=[bed_trace])

    # Calculate aspect ratio relative to the domain size for realistic X/Y,
    # and exaggerate Z relative to X/Y for better visibility of topography differences.
    domain_dx = maxx - minx
    domain_dy = maxy - miny
    plot_z_range_aspect = plot_z_max - plot_z_min # Use plotting range for Z aspect


    # Avoid division by non-positive numbers
    aspect_x = 1.0
    aspect_y = (domain_dy / domain_dx) if domain_dx > 0 else 1.0
    # Exaggerate Z relative to X. Factor 0.5 provides some visual boost.
    aspect_z = (plot_z_range_aspect / domain_dx * 0.5) if domain_dx > 0 and plot_z_range_aspect > 0 else 0.5

    # Ensure finite values (though >0 check handles most cases)
    if not np.isfinite(aspect_x): aspect_x = 1.0
    if not np.isfinite(aspect_y): aspect_y = 1.0
    if not np.isfinite(aspect_z): aspect_z = 0.5


    fig.update_layout(
        title="Loaded Bedrock Topography (1981 Surface used as Bed)",
        scene=dict(
            xaxis_title='Easting (m)',
            yaxis_title='Northing (m)',
            zaxis_title='Elevation (m)',
            xaxis=dict(range=[minx, maxx]),
            yaxis=dict(range=[miny, maxy]),
            zaxis=dict(range=[plot_z_min, plot_z_max]), # Use dynamic Z range
            aspectmode='manual',
            aspectratio=dict(x=aspect_x, y=aspect_y, z=aspect_z),

             camera=dict( # Initial camera position for a good overview
                up=dict(x=0, y=0, z=1),
                center=dict(x= (minx+maxx)/2, y= (miny+maxy)/2, z=(plot_z_min+plot_z_max)/2), # Center camera on domain
                eye=dict(x=1.5, y=-1.5, z=1.0) # Adjust initial viewing angle relative to center
            )
        ),
        margin=dict(l=0, r=0, t=60, b=0),
        uirevision="bedrock_only", # A fixed uirevision keeps the view consistent on reruns in Phase 1
        plot_bgcolor='#f9f9f9', # Light background for plot area
        paper_bgcolor='#fff', # White background for paper area
        height=700 # Fixed figure height
    )

    return fig


# --- Streamlit App Execution Flow ---

st.write("This application will simulate a glacier using a 2D grid based on real topography.")
st.markdown("---")

# --- Action Required Check ---
if DEM_PATH == "path/to/your/1981Yala_dem_20_-10_bias_cor.tif":
    st.error("Please update the `DEM_PATH` variable at the top of the script with the actual file path to your 1981 Yala Glacier DEM.")
    st.stop()


# Define the actual bounding box tuple
BBOX_LONLAT = (BBOX_LON_MIN, BBOX_LAT_MIN, BBOX_LON_MAX, BBOX_LAT_MAX)


# Load and process the DEM (this will be cached by Streamlit)
# This section now includes more debug messages and error handling
processed_data = load_and_process_dem_cached(DEM_PATH, BBOX_LONLAT, GRID_RESOLUTION, UTM_CRS_EPSG)

# Store the results from the cached function into Streamlit's session state
# This makes the data available across app reruns without reprocessing the DEM
# We access results by index from the tuple returned by the cached function
st.session_state['bed_elevation_np'] = processed_data[0]
st.session_state['X_grid_np'] = processed_data[1]
st.session_state['Y_grid_np'] = processed_data[2]
st.session_state['domain_bounds'] = processed_data[3]
st.session_state['target_transform'] = processed_data[4]
Ny, Nx = st.session_state['bed_elevation_np'].shape


# --- Initialize Simulation State (For Future Phases) ---
# Initialize ice thickness, step counter, and running flag if they don't exist in session state.
if 'ice_thickness_np' not in st.session_state:
    st.session_state['ice_thickness_np'] = np.zeros((Ny, Nx))
    st.session_state['current_step'] = 0
    st.session_state['sim_running'] = False
    # Mask the initial ice thickness with NaN where the bed is NaN (off the land)
    # Use np.copy to avoid modifying the zeros array reference directly
    st.session_state['ice_thickness_np'] = st.session_state['ice_thickness_np'].copy()
    st.session_state['ice_thickness_np'][np.isnan(st.session_state['bed_elevation_np'])] = np.nan

    st.info("Initial simulation state (zero ice thickness) initialized in session_state.")


# --- Display the Bedrock Plot (Phase 1 Output) ---

st.markdown("---")
st.subheader("Bedrock Topography from DEM")
st.write("This 3D plot shows the elevation of the bedrock (using the 1981 ice surface DEM as a proxy) that the glacier simulation will run on.")


# Create and display the figure showing only the bedrock
# Use data directly from session state
bedrock_figure = create_bedrock_figure(
    st.session_state['bed_elevation_np'],
    st.session_state['X_grid_np'],
    st.session_state['Y_grid_np'],
    st.session_state['domain_bounds']
)

# Use st.container to create a placeholder for the plot that can be updated later (for animation)
# In Phase 1, it's just the initial display, but structure is set for future phases
plot_container = st.empty()
plot_container.plotly_chart(bedrock_figure, use_container_width=True)


st.markdown("---")
st.write(f"Data loaded for grid size: {Nx} columns x {Ny} rows ({GRID_RESOLUTION}m resolution).")
st.write(f"Easting Range: {st.session_state['domain_bounds'][0]:.0f} m to {st.session_state['domain_bounds'][2]:.0f} m")
st.write(f"Northing Range: {st.session_state['domain_bounds'][1]:.0f} m to {st.session_state['domain_bounds'][3]:.0f} m")
bed_min_display = np.nanmin(st.session_state['bed_elevation_np']) if np.any(~np.isnan(st.session_state['bed_elevation_np'])) else np.nan
bed_max_display = np.nanmax(st.session_state['bed_elevation_np']) if np.any(~np.isnan(st.session_state['bed_elevation_np'])) else np.nan
st.write(f"Elevation Range: {bed_min_display:.2f} m to {bed_max_display:.2f} m (NaNs ignored)")


st.success("Phase 1 Debug: Attempted to load and display bedrock topography.")
st.info("If you see the plot, it was successful! If there's an error message above this, read it carefully.")


# --- End of Phase 1 Debug Code ---