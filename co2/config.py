# co2/config.py
# Every CO2-specific constant and user-facing explanation, in one place.
# See NOTES.md for the measurements behind these values.

# ---- Sources ----------------------------------------------------------------
# CO2 isn't in Earth Engine; these come from NASA's GHG Center (STAC + a
# titiler raster API that does zonal stats over HTTP).
STAC_API = "https://earth.gov/ghgcenter/api/stac"
RASTER_API = "https://earth.gov/ghgcenter/api/raster"

# cell_deg decides whether an AOI is answerable at all — see analysis.adequacy().
SOURCES = {
    "xco2_grid": {
        "collection": "oco2geos-co2-daygrid-v10r",
        "asset": "xco2",
        "label": "OCO-2 GEOS assimilated XCO2",
        "unit": "ppm",
        "cadence": "daily",
        "cell_deg": (0.5, 0.625),          # lat, lon
        "coverage": ("2015-01-01", "2022-02-28"),
        "kind": "assimilation",
        "what_it_is":
            "A transport model, corrected every six hours by real OCO-2 "
            "soundings that may be hundreds of km away. Gap-free because the "
            "model fills the gaps, not because the satellite saw everywhere.",
    },
    "sam": {
        "collection": "oco3-co2-sams-daygrid-v11r",
        "asset": "cog_default",
        "label": "OCO-2/3 targeted snapshots",
        "unit": "ppm",
        "cadence": "opportunistic",
        "cell_deg": (0.02, 0.02),          # ~2 km
        "coverage": ("2014-09-07", "2025-09-29"),
        "kind": "observation",
        "what_it_is":
            "OCO-2/3 pointed at a site for one overpass, at about 2 km "
            "resolution. Real soundings, but only where and when the "
            "satellite was aimed — no guaranteed coverage.",
    },
    "odiac": {
        "collection": "odiac-ffco2-monthgrid-v2024",
        "asset": "co2-emissions",
        "label": "ODIAC fossil-fuel CO2 emissions",
        "unit": "tonne C / cell / month",
        "cadence": "monthly",
        "cell_deg": (1 / 120, 1 / 120),    # 1 km
        "coverage": ("2000-01-01", "2023-12-31"),
        "kind": "inventory",
        "what_it_is":
            "A bottom-up inventory: national fossil-fuel totals spread "
            "across a 1 km grid using night-lights and power-plant "
            "locations. Models where CO2 is emitted; measures nothing.",
    },
}

# ODIAC reports tonnes of *carbon*, not CO2 (12 g/mol vs 44 g/mol).
CARBON_TO_CO2 = 44.0 / 12.0

# A few XCO2 days are all-zero rasters, not masked nodata, and get counted as
# valid — anything under this floor (XCO2 has never been this low) is a broken file.
MIN_PLAUSIBLE_PPM = 300.0

# ---- When an area is too small to answer -------------------------------------
# A city AOI (0.3°) is smaller than one XCO2 cell (0.5 x 0.625°) — any number
# for it would be interpolation, not a measurement, so the page declines.
MIN_CELLS_FOR_READING = 4        # a 2x2 block; below this, no number is shown
MIN_CELLS_FOR_PATTERN = 25       # below this, no spatial pattern is claimed

# ---- Detrending and deseasonalising ------------------------------------------
# CO2's seasonal swing and yearly rise dwarf a city's own contribution by two
# orders of magnitude, so both must be removed before anything else is read.
MIN_YEARS_FOR_TREND = 2.0        # below this a slope is noise, not a trend
MIN_YEARS_FOR_SEASONAL = 3.0     # a seasonal shape needs repeats to average
TREND_SAMPLE_DAYS = 7            # weekly is plenty for an 8 ppm annual wave

# ---- NO2-inferred combustion CO2 ---------------------------------------------
# Combustion emits CO2 and NOx together; NO2 is destroyed within hours (never
# accumulates) while CO2 accumulates for centuries, so the visible NO2 is
# scaled by their emission ratio. That ratio is uncertain per mole, hence a
# range: low end NOx-rich/older diesel, high end efficient with NOx control.
EMISSION_RATIOS = {
    "low": 500.0,        # mol CO2 per mol NOx — NOx-rich combustion
    "central": 1200.0,   # a mixed urban/industrial plume
    "high": 3000.0,      # efficient combustion with NOx controls
}

# Moles of dry air per m^2 column at standard pressure — converts the
# inferred CO2 column (umol/m2) into ppm.
DRY_AIR_COLUMN_MOL_M2 = 101325.0 / (9.81 * 0.02896)

# Must stay identical to no2/config.py so the two pages never disagree.
NO2_ASSET = "COPERNICUS/S5P/OFFL/L3_NO2"

# Tropospheric, not total — the total's stratospheric part would understate
# the enhancement.
NO2_BAND = "tropospheric_NO2_column_number_density"

NO2_UNIT_SCALE = 1e6             # mol/m2 -> umol/m2
NO2_REDUCE_SCALE = 5500          # the TROPOMI UV/VIS footprint (3.5 x 5.5 km)
NO2_BACKGROUND_SCALE = 15000     # coarser: the background box is much larger
NO2_COVERAGE_START = "2018-06-28"

# ---- Level bands --------------------------------------------------------------
# Banded on the deseasonalised, detrended anomaly in ppm. Day-to-day scatter
# inside a province-sized box runs 0.3-1.1 ppm, so anything under 0.5 ppm is
# reported as within noise rather than a detection.
ANOMALY_LEVELS = [
    (-0.5,         "Below background",   "#2e7d32"),
    (0.5,          "Within noise",       "#78909c"),
    (1.5,          "Slightly elevated",  "#ffc107"),
    (3.0,          "Elevated",           "#ff6f00"),
    (float("inf"), "Strongly elevated",  "#c62828"),
]
LEVEL_UNIT = "ppm"
LEVEL_TITLE = "XCO2 anomaly after trend and season are removed"

# ---- Styling -------------------------------------------------------------------
ACCENT = "#2e7d32"
# titiler colormap names: the raster is coloured server-side before the tile
# reaches the browser.
XCO2_COLORMAP = "magma"
ODIAC_COLORMAP = "inferno"
SAM_COLORMAP = "magma"
# ODIAC spans six orders of magnitude, so class intervals (each ~3x the
# last) instead of a linear ramp; in CO2 to match the page's metrics.
ODIAC_CO2_BREAKS = (5.0, 15.0, 50.0, 200.0, 1000.0, 5000.0)

# Pale yellow to deep red, alpha climbing alongside so the faintest class
# stays legible over a basemap and the top class survives being 1-2 cells wide.
ODIAC_CLASS_COLORS = (
    ("#ffffb2", 140), ("#fed976", 170), ("#feb24c", 195), ("#fd8d3c", 215),
    ("#fc4e2a", 235), ("#e31a1c", 250), ("#b10026", 255),
)
SAM_PAD_PPM = 0.5                # stretch a snapshot around its own range

SEASON_UP_COLOR = "#8d6e63"      # air giving CO2 back (autumn/winter)
SEASON_DOWN_COLOR = "#2e7d32"    # plants taking it up (growing season)

# ---- The reality checks --------------------------------------------------------
# Printed next to the numbers they qualify, not in a separate docs page.

WHY_TREND = (
    "<b>CO2 is rising globally, year after year</b> — total human emissions "
    "accumulating in the atmosphere, not something specific to this area. "
    "That rise has to be removed before two years can be compared."
)

# The general explanation. Where a measured amplitude exists for the area on
# screen, why_seasonal() below appends it.
WHY_SEASONAL = (
    "<b>Northern Hemisphere plants pull CO2 out of the air each summer and "
    "release it over winter.</b> The swing is hundreds of times larger than "
    "anything one city or oil field adds."
)

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November",
                "December"]


def why_seasonal(label=None, amplitude=None, high_month=None, low_month=None):
    """WHY_SEASONAL, with this area's own measured cycle appended."""
    if amplitude is None or high_month is None or low_month is None:
        return WHY_SEASONAL
    return (
        f"{WHY_SEASONAL}<br><br>Over <b>{label or 'this area'}</b> the "
        f"measured swing is <b>{amplitude:.2f} ppm</b>, between a high in "
        f"{_MONTH_NAMES[high_month - 1]} and a low in "
        f"{_MONTH_NAMES[low_month - 1]}.")


def why_deseasonalise(label=None, amplitude=None, slope=None):
    """WHY_DESEASONALISE, stated in this area's own numbers where known."""
    if amplitude is None or slope is None:
        return WHY_DESEASONALISE
    return (
        f"<b>Why two dates can't just be compared.</b> Over "
        f"<b>{label or 'this area'}</b> CO2 moves <b>{amplitude:.2f} ppm</b> "
        f"across the season and rises <b>{slope:.2f} ppm</b> a year — a "
        f"hundred times a whole city's own contribution. Both have to be "
        f"subtracted first.")

WHY_DESEASONALISE = (
    "<b>Why two dates can't just be compared.</b> The seasonal swing and the "
    "yearly rise are each a hundred times larger than a city's own "
    "contribution to CO2, so both have to be removed before a difference "
    "means anything."
)

WHY_LAND_COVER = (
    "<b>The surrounding box isn't a clean control here.</b> It reflects "
    "plant cover as well as air — Alberta reads 0.47 ppm below its own "
    "surrounding box in July purely from vegetation, not emissions."
)

WHY_TOO_SMALL = (
    "<b>Your area is smaller than the data's resolution.</b> The XCO2 grid "
    "cell is about 55 × 40 km; a city fits inside one cell, so a number for "
    "it would be interpolation, not a measurement."
)

WHY_NO_CO2_ENHANCEMENT = (
    "<b>Expect \"within noise,\" and believe it.</b> A single city's CO2 is "
    "a rounding error on the global background — Edmonton measured +0.014 "
    "ppm in July 2021. Use the NO2-inferred tab for a city-scale signal."
)

WHY_INFERRED = (
    "<b>Inferred, not measured.</b> No satellite saw this CO2 — NO2, "
    "combustion's visible partner gas, was scaled by their emission ratio "
    "instead, which is uncertain by several times. That's why a range is "
    "shown, and why venting, cement or land-use CO2 (no NOx) is invisible "
    "to it."
)
