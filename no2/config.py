# no2/config.py
# NO2-specific settings (product, band, units, thresholds, colour); backend.py
# reads all of it from here, so retuning doesn't mean editing the pipeline.

# ---- Product ----------------------------------------------------------------
# UV/VIS, finer footprint than CH4/CO's SWIR. OFFL (reprocessed), not NRTI.
NO2_ASSET = "COPERNICUS/S5P/OFFL/L3_NO2"

# Tropospheric column, not total: the total column is dominated by smooth,
# seasonal/latitude-driven stratospheric NO2 and would bury surface sources.
NO2_BAND = "tropospheric_NO2_column_number_density"
COVERAGE_START = "2018-06-28"      # first OFFL L3 NO2 image in Earth Engine

# ---- Units ------------------------------------------------------------------
# Column is in mol/m2 (like CO, unlike CH4). Scaled to umol/m2 once here, in
# Earth Engine, so histogram buckets aren't unusably narrow; nothing downstream converts.
UNIT_SCALE = 1e6                   # mol/m2 -> umol/m2
UNIT = "µmol/m²"

# For comparing against literature, usually quoted in molec/cm2.
MOLEC_CM2_PER_UMOL_M2 = 6.022e13

# ---- Reduction scales -------------------------------------------------------
REDUCE_SCALE = 5500        # metres: the TROPOMI footprint, not the asset's
                           # own 0.01-degree (1113.2 m) publication grid
BACKGROUND_SCALE = 15000   # coarser, since the background box is much larger
HISTOGRAM_BUCKETS = 64     # ceiling; EE picks the bucket width from the range

# ---- Classification ---------------------------------------------------------
# Banded on percent above background, not absolute (unlike CH4): NO2's short
# lifetime means a regional background that shifts with season/urbanization.
EMISSION_LEVELS = [
    # (upper bound of enhancement in % of background, label, colour)
    (0.0,          "Below background", "#2e7d32"),   # green
    (10.0,         "Low",              "#9acd32"),   # yellow-green
    (30.0,         "Moderate",         "#ffc107"),   # amber
    (80.0,         "Elevated",         "#ff6f00"),   # orange
    (float("inf"), "High",             "#c62828"),   # red
]
LEVEL_UNIT = "%"
LEVEL_TITLE = "NO2 enhancement vs local background"

# ---- Raster styling ---------------------------------------------------------
# White-through-pink-to-dark-magenta ramp, chosen to stay visually distinct
# from CH4's navy-to-red and CO's black-to-yellow when maps sit side by side.
NO2_PALETTE = [
    "#f7f4f9", "#e7e1ef", "#d4b9da", "#c994c7",
    "#df65b0", "#dd1c77", "#980043",
]

# Hotspot outlines drawn in bright green since the ramp above never reaches green.
HOTSPOT_COLOR = "#00e676"
HOTSPOT_TEXT_COLOR = "#00331a"   # the green is far too light to carry white

# Fallback stretch (umol/m2), used when the AOI's own 2nd/98th percentiles are
# missing or degenerate.
NO2_VIS_FALLBACK = (0.0, 100.0)
# Minimum spread before the percentile stretch is trusted over the fallback.
MIN_VIS_SPREAD = 1.0

# ---- Hotspot reporting ------------------------------------------------------
MAX_HOTSPOT_REGIONS = 40     # patches returned by the backend, hottest first
DEFAULT_HOTSPOT_REGIONS = 8  # boxes the map draws until the slider says otherwise
