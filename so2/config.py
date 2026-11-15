# so2/config.py
# SO2-specific settings (product, band, units, thresholds, colour); backend.py
# reads all of it from here. SO2 is by far the noisiest product — see EMISSION_LEVELS.

# ---- Product ----------------------------------------------------------------
# UV, like NO2, same platform/overpass/footprint, unlike CH4/CO's SWIR.
SO2_ASSET = "COPERNICUS/S5P/OFFL/L3_SO2"

# Boundary-layer column (right for ground sources); the asset's alternate
# 15km-plume-height band is for volcanic eruptions and understates ground sources.
SO2_BAND = "SO2_column_number_density"
COVERAGE_START = "2018-11-28"      # first OFFL L3 SO2 image (verified via
                                   # aggregate_min; NOT the 2018-07-10 NRTI start)

# ---- Units ------------------------------------------------------------------
# Vertical column in mol/m2, scaled once in Earth Engine to umol/m2 (not CO's
# mmol/m2 — SO2 is two orders smaller, so mmol/m2 reads as unreadable 0.025s).
UNIT_SCALE = 1e6                   # mol/m2 -> umol/m2
UNIT = "µmol/m²"

# ---- Reduction scales -------------------------------------------------------
REDUCE_SCALE = 5500        # metres: the TROPOMI footprint, not the asset's
                           # own 0.01-degree (1113.2 m) publication grid
BACKGROUND_SCALE = 15000   # coarser, since the background box is much larger
HISTOGRAM_BUCKETS = 64     # ceiling; EE picks the bucket width from the range

# ---- Classification ---------------------------------------------------------
# Banded on *absolute* enhancement (like CH4, unlike CO/NO2): SO2's background
# is small and scatters around zero, so a percentage would blow up or flip sign.
EMISSION_LEVELS = [
    # (upper bound umol/m2, label, colour). -50 (not 0) anchors "Within noise"
    # so negative readings (common here) don't read as "Below background".
    (-50.0,        "Below background", "#2e7d32"),   # green
    (50.0,         "Within noise",     "#78909c"),   # grey: not a detection
    (150.0,        "Low",              "#ffc107"),   # amber
    (400.0,        "Moderate",         "#ff6f00"),   # orange
    (float("inf"), "High",             "#c62828"),   # red
]
LEVEL_UNIT = UNIT
LEVEL_TITLE = "SO2 enhancement vs local background"

# Shown under the headline metric, so a reader who looks at one number and
# stops still gets told what it is worth.
NOISE_NOTE = (
    "SO2 is the noisiest of the four products: over clean air the retrieval "
    "scatters around zero and individual pixels often come back negative. An "
    "enhancement inside ±50 µmol/m² is reported as <b>Within noise</b> — it "
    "is not a detection. TROPOMI sees SO2 reliably from strong sources, which "
    "run into the hundreds."
)

# ---- Raster styling ---------------------------------------------------------
# Pale-yellow-through-teal-to-dark-blue ramp, matching this gas's badge colour
# on the dashboard and distinct from the other three maps.
SO2_PALETTE = [
    "#ffffd9", "#c7e9b4", "#7fcdbb", "#41b6c4",
    "#1d91c0", "#225ea8", "#0c2c84",
]

# Hotspot outlines sit on top of that ramp, which never reaches orange.
HOTSPOT_COLOR = "#ff6d00"
HOTSPOT_TEXT_COLOR = "#ffffff"

# Fallback stretch (umol/m2), used when the AOI's own 2nd/98th percentiles are
# missing or degenerate. Starts below zero on purpose: so does the data.
SO2_VIS_FALLBACK = (-50.0, 200.0)
# Minimum spread before the percentile stretch is trusted over the fallback;
# higher than the other gases' since a narrow spread here is more likely a quiet retrieval.
MIN_VIS_SPREAD = 10.0

# ---- Hotspot reporting ------------------------------------------------------
MAX_HOTSPOT_REGIONS = 40     # patches returned by the backend, hottest first
DEFAULT_HOTSPOT_REGIONS = 8  # boxes the map draws until the slider says otherwise
