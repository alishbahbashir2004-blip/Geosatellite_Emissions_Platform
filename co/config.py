# co/config.py
# CO-specific constants: product/band, units, thresholds, raster colours.
# backend.py reads all of it, so retuning the agent doesn't mean editing it.

# ---- Product ----------------------------------------------------------------
# Same SWIR band/overpass as the CH4 agent, so same-day CO and CH4 share
# photons. OFFL (reprocessed), not NRTI — NRTI is noisier for CO.
CO_ASSET = "COPERNICUS/S5P/OFFL/L3_CO"
CO_BAND = "CO_column_number_density"
CLOUD_BAND = "cloud_height"
COVERAGE_START = "2018-07-04"      # first OFFL L3 CO image in Earth Engine

# ---- Units ------------------------------------------------------------------
# Total column (mol/m2), not a mixing ratio — no ppb, CH4's thresholds don't
# carry over. Scaled to mmol/m2 once here; nothing downstream converts further.
UNIT_SCALE = 1000.0                # mol/m2 -> mmol/m2
UNIT = "mmol/m²"
UNIT_SHORT = "mmol/m²"

DRY_AIR_COLUMN_MOL_M2 = 3.57e5  # context only, unused by the page

# ---- Cloud filtering --------------------------------------------------------
# Over cloud, CO retrieval sees only the column above it, not the ground.
# cloud_height (scattering height), low = near-surface; 500 m keeps most pixels.
DEFAULT_CLOUD_CEILING_M = 500.0
CLOUD_CEILING_CHOICES = (300.0, 500.0, 1000.0, 2000.0)
CLEAR_SKY_DEFAULT = True

# ---- Reduction scales -------------------------------------------------------
REDUCE_SCALE = 7000        # metres: TROPOMI footprint (5.5x7 km; 7x7 km pre-Aug
                           # 2019), not the asset's native 0.01-deg (1113.2 m) grid
BACKGROUND_SCALE = 15000   # coarser: background box is much larger
HISTOGRAM_BUCKETS = 64     # ceiling; EE picks the bucket width from the range

# ---- Classification ---------------------------------------------------------
# Banded on percent above background (opposite of CH4's absolute ppb): CO's
# background swings with latitude/season/fires, so percent travels where a fixed cut would not.
EMISSION_LEVELS = [
    # (upper bound of enhancement in % of background, label, colour)
    (0.0,          "Below background", "#2e7d32"),   # green
    (5.0,          "Low",              "#9acd32"),   # yellow-green
    (15.0,         "Moderate",         "#ffc107"),   # amber
    (40.0,         "Elevated",         "#ff6f00"),   # orange
    (float("inf"), "High",             "#c62828"),   # red
]
LEVEL_UNIT = "%"
LEVEL_TITLE = "CO enhancement vs local background"

# ---- Regional loading -------------------------------------------------------
# Confounder unique to CO: wildfire smoke raises the whole scene's background
# (percent-enhancement already accounts for it; this table surfaces it).
REGIONAL_LOADING_LEVELS = [
    (35.0,         "Clean",     "#2e7d32"),
    (50.0,         "Moderate",  "#ffc107"),
    (80.0,         "High",      "#ff6f00"),
    (float("inf"), "Very high", "#c62828"),
]
LOADING_UNIT = UNIT
LOADING_TITLE = "Regional CO loading (background column)"

LOADING_NOTES = {
    "Clean": "Background column is in the normal range — an enhancement here "
             "stands on clean air.",
    "Moderate": "Background column is somewhat raised. Some regional "
                "pollution or distant smoke is likely present.",
    "High": "Background column is well above normal — probably smoke or "
            "long-range transport across the whole scene. The enhancement "
            "below is measured against that raised background, so it is "
            "still local, but the scene is not clean.",
    "Very high": "Background column is very high. The scene is almost "
                 "certainly inside a smoke plume; treat any local "
                 "attribution with caution.",
}

# ---- Raster styling ---------------------------------------------------------
# Inferno-style ramp, distinct from the CH4 agent's navy-to-red ramp so the
# two maps are never confused at a glance.
CO_PALETTE = [
    "#000004", "#320a5a", "#781c6d", "#bb3654",
    "#ed6925", "#fbb61a", "#fcffa4",
]

HOTSPOT_COLOR = "#00e5ff"   # cyan: the one hue the ramp above never touches

# Fallback stretch (mmol/m2) when the AOI's percentiles are missing/degenerate.
CO_VIS_FALLBACK = (20.0, 60.0)
MIN_VIS_SPREAD = 0.5  # min spread (mmol/m2) before trusting the percentile stretch

# ---- Hotspot reporting ------------------------------------------------------
# Two separate numbers: how many patches the backend returns vs. how many the
# map draws by default (the slider adjusts the latter without re-querying EE).
MAX_HOTSPOT_REGIONS = 40     # patches returned by the backend, hottest first
DEFAULT_HOTSPOT_REGIONS = 8  # boxes the map draws until the slider says otherwise
