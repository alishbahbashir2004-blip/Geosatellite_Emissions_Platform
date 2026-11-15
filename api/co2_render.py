# api/co2_render.py
# CO2's charts and maps as data (see api/render.py). Separate module because
# CO2 has four map kinds (grid lattice, emissions raster, snapshot footprint,
# boxes-only) instead of the other gases' single raster-plus-hotspots shape.
# Figures/geometry come from co2/chartview.py and co2/mapview.py; this only
# flattens them into JSON.

from co2 import chartview, mapview
from co2.config import SOURCES, ACCENT

GRID_COLOR = "#ffffff"
AOI_COLOR = "#1f77b4"
BACKGROUND_COLOR = "#8e6bbf"
FOOTPRINT_COLOR = "#ff6d00"
MAX_LATTICE_LINES = 120


def _chart(builder, *args):
    try:
        chart = builder(*args)
    except Exception:
        return None
    return None if chart is None else chart.to_dict()


def _box(bbox, color, tooltip, weight=3, fill=0.10, dash=None):
    return {"bbox": bbox, "color": color, "tooltip": tooltip,
            "weight": weight, "fillOpacity": fill, "dash": dash,
            "badge": None}


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def coverage_chart(rows, date_start, date_end):
    return _chart(chartview.build_coverage_chart, rows, date_start, date_end)


def trend_charts(result, date_start, date_end):
    return {
        "record": _chart(chartview.build_record_chart, result,
                         date_start, date_end),
        "seasonal": _chart(chartview.build_seasonal_chart, result),
        "remainder": _chart(chartview.build_remainder_chart, result),
    }


def anomaly_charts(result):
    return {"anomaly": _chart(chartview.build_anomaly_chart, result)}


def inventory_charts(result):
    return {"monthly": _chart(chartview.build_inventory_chart, result)}


def snapshot_charts(result):
    return {
        "histogram": _chart(chartview.build_snapshot_histogram, result),
        "timeline": _chart(chartview.build_snapshot_timeline, result),
    }


def inferred_charts(result, measured_ppm=None):
    return {"range": _chart(chartview.build_inferred_chart, result,
                            measured_ppm)}


# ---------------------------------------------------------------------------
# Maps
# ---------------------------------------------------------------------------

def grid_map(bbox, source_key, adequacy, background_bbox=None,
             label="Selected area"):
    """The AOI with the product's real grid cells ruled over it.

    Lattice is snapped to the product's own cell origin (not the AOI corner)
    so the lines drawn match the real cells, and is skipped if too dense.
    """
    cell_lat, cell_lon = SOURCES[source_key]["cell_deg"]
    extent = background_bbox or bbox
    boxes, lines = [], []

    if background_bbox:
        boxes.append(_box(background_bbox, BACKGROUND_COLOR,
                          "Surrounding box used as the local background",
                          dash="8,6", fill=0.04))

    span_lat = extent["N"] - extent["S"]
    span_lon = extent["E"] - extent["W"]
    if span_lat / cell_lat + span_lon / cell_lon <= MAX_LATTICE_LINES:
        row = extent["S"] - (extent["S"] % cell_lat)
        while row < extent["N"] + cell_lat:
            lines.append({"coords": [[row, extent["W"]], [row, extent["E"]]],
                          "color": GRID_COLOR, "weight": 1, "opacity": 0.55})
            row += cell_lat
        column = extent["W"] - (extent["W"] % cell_lon)
        while column < extent["E"] + cell_lon:
            lines.append({"coords": [[extent["S"], column],
                                     [extent["N"], column]],
                          "color": GRID_COLOR, "weight": 1, "opacity": 0.55})
            column += cell_lon

    km_lat, km_lon = adequacy["cell_km"]
    boxes.append(_box(
        bbox, AOI_COLOR,
        f"{label} — spans {adequacy['cells']:.1f} "
        f"{SOURCES[source_key]['label']} cells (one cell is about "
        f"{km_lat:.0f} x {km_lon:.0f} km here)", fill=0.12))

    return {"fit": extent, "tiles": [], "boxes": boxes, "lines": lines,
            "colorbar": None}


def inventory_map(result):
    """The ODIAC 1 km emissions raster under the AOI outline.

    Class intervals instead of a colour bar: ODIAC spans six orders of
    magnitude, so a linear ramp would render as a flat block.
    """
    latest = result["latest"]
    return {
        "fit": result["bbox"],
        "tiles": [{"url": result["tile_url"],
                   "name": "Fossil-fuel CO2 emissions (ODIAC, 1 km)",
                   "opacity": 0.80, "show": True}],
        "boxes": [_box(result["bbox"], AOI_COLOR,
                       f"{result['label']} — "
                       f"{latest['mean_tco2_per_km2_month']:,.0f} "
                       f"t CO2/km²/month in {latest['date'][:7]}", fill=0.0)],
        "lines": [],
        "colorbar": None,
        "classLegend": {
            "title": "Fossil-fuel CO2 — tonnes per 1 km cell per month",
            "note": ("Uncoloured land emits nothing at all in this inventory "
                     "— that is missing data, not zero."),
            "classes": [{"low": low, "high": high, "color": color}
                        for low, high, color in result["classes"]],
        },
    }


def snapshot_map(result):
    """One targeted snapshot, with the footprint it actually covered.

    Footprint is drawn because it rarely matches the AOI — the satellite was
    aimed at a target, not the user's box, and the rest of the box has no
    data on that date.
    """
    footprint, bbox = result["footprint"], result["bbox"]
    stats = result["stats"]
    low, high = result["rescale"]
    union = {"N": max(footprint["N"], bbox["N"]),
             "S": min(footprint["S"], bbox["S"]),
             "W": min(footprint["W"], bbox["W"]),
             "E": max(footprint["E"], bbox["E"])}
    return {
        "fit": union,
        "tiles": [{"url": result["tile_url"],
                   "name": f"XCO2 soundings — {result['chosen']['date']}",
                   "opacity": 0.85, "show": True}],
        "boxes": [
            _box(footprint, FOOTPRINT_COLOR,
                 f"Snapshot footprint — {result['covered_km2']:,.0f} km² "
                 f"measured, mean {stats['mean']:.2f} ppm, "
                 f"spread {result['spread']:.2f} ppm",
                 dash="8,6", fill=0.0, weight=2),
            _box(bbox, AOI_COLOR, f"{result['label']} (your selection)",
                 fill=0.0),
        ],
        "lines": [],
        "colorbar": {"colors": list(mapview.MAGMA), "vmin": float(low),
                     "vmax": float(high), "caption": "XCO2 (ppm)"},
    }


def inferred_map(result):
    """The two boxes the NO2 enhancement was measured between.

    No raster on purpose: this tab's quantity is a difference between two
    areas, and an NO2 layer would invite reading CO2 off it directly.
    """
    return {
        "fit": result["background_bbox"],
        "tiles": [],
        "boxes": [
            _box(result["background_bbox"], BACKGROUND_COLOR,
                 f"Local background — NO2 "
                 f"{result['no2_background']:.1f} µmol/m²",
                 dash="8,6", fill=0.04),
            _box(result["bbox"], ACCENT,
                 f"{result['label']} — NO2 {result['no2_aoi']:.1f} µmol/m² "
                 f"({result['no2_delta']:+.1f} vs background)", fill=0.12),
        ],
        "lines": [],
        "colorbar": None,
    }
