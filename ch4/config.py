# ch4/config.py
# Methane-specific constants: product/band, units, thresholds, raster colours.
# backend.py reads all of it, so retuning the agent doesn't mean editing it.

# ---- Product ----------------------------------------------------------------
# Same SWIR band/overpass as the CO agent, so same-day CH4 and CO share photons.
# OFFL (reprocessed), not NRTI, for retrospective analysis.
CH4_ASSET = "COPERNICUS/S5P/OFFL/L3_CH4"
# Bias-corrected, not raw: AOI vs. background box differ in land cover/bias,
# so raw-vs-corrected does not cancel between them. NOTE: EMISSION_LEVELS was
# tuned on raw figures, not re-measured since — bands currently read low.
CH4_BAND = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
COVERAGE_START = "2018-11-28"      # first OFFL L3 CH4 image in Earth Engine

# ---- Units ------------------------------------------------------------------
# Already ppb (unlike CO, which arrives as mol/m2 and needs conversion).
UNIT = "ppb"

# ---- Reduction scales -------------------------------------------------------
REDUCE_SCALE = 7000        # metres: TROPOMI footprint (5.5x7 km), not the
                           # asset's native 0.01-deg (1113.2 m) grid
BACKGROUND_SCALE = 15000   # coarser: background box is much larger
HISTOGRAM_BUCKETS = 64     # ceiling; EE snaps to the largest power-of-2 width under it

# ---- Classification ---------------------------------------------------------
# Banded on absolute ppb (opposite of CO's percent): CH4 is long-lived/well-mixed,
# so a fixed ppb means the same everywhere. Cuts follow typical basin enhancements.
EMISSION_LEVELS = [
    # (upper bound of enhancement in ppb, label, colour)
    (0.0,          "Below background", "#2e7d32"),   # green
    (5.0,          "Low",              "#9acd32"),   # yellow-green
    (12.0,         "Moderate",         "#ff8c00"),   # orange
    (float("inf"), "High",             "#d32f2f"),   # red
]
LEVEL_UNIT = UNIT
LEVEL_TITLE = "Emission level vs local background"

# ---- Raster styling ---------------------------------------------------------
# Navy-through-cyan-yellow-to-dark-red, distinct from the CO agent's inferno
# ramp so the two maps are never confused at a glance.
CH4_PALETTE = [
    "#000080", "#0000d0", "#00d0ff", "#40ffff",
    "#ffff00", "#ff8000", "#ff0000", "#800000",
]

HOTSPOT_COLOR = "#ff00ff"       # magenta: the one hue the ramp above never uses
HOTSPOT_TEXT_COLOR = "#ffffff"

# Fallback stretch (ppb) when the AOI's own 2nd/98th percentiles are missing
# or degenerate.
CH4_VIS_FALLBACK = (1750.0, 1950.0)
MIN_VIS_SPREAD = 1.0   # minimum spread (ppb) before trusting the percentile stretch

# ---- Hotspot reporting ------------------------------------------------------
# Two separate numbers: how many patches the backend returns vs. how many the
# map draws by default (the slider adjusts the latter without re-querying EE).
MAX_HOTSPOT_REGIONS = 40     # patches returned by the backend, hottest first
DEFAULT_HOTSPOT_REGIONS = 8  # boxes the map draws until the slider says otherwise
