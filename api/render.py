# api/render.py
# Turns a Python result into chart specs and a map description for React.
#
# Charts: Altair *is* Vega-Lite, so `chart.to_dict()` is handed to the client
# untouched and rendered by vega-embed. Maps: emitted as layers/rectangles/
# colour-bar data (not Folium HTML) for react-leaflet to draw, using each
# gas's own MapSpec the same way shared/mapview.py does.

from shared.mapview import UNKNOWN_COLOR
from api.specs import modules

AOI_WEIGHT = 3
HOTSPOT_WEIGHT = 2.5


def _chart(builder, *args):
    """A chart's Vega-Lite spec, or None when the gas declines to draw it."""
    try:
        chart = builder(*args)
    except Exception:
        return None
    return None if chart is None else chart.to_dict()


# ---------------------------------------------------------------------------
# Sentinel-5P gases
# ---------------------------------------------------------------------------

def charts(key, result):
    """Every figure the gas's page draws, as Vega-Lite specs."""
    chartview = modules(key)["chartview"]
    return {
        "series": _chart(chartview.build_series_chart, result),
        "availability": _chart(chartview.build_availability_chart, result),
        "box": _chart(chartview.build_box_plot, result),
        "histogram": _chart(chartview.build_histogram_chart, result),
        "backgroundHistogram": _chart(chartview.build_bg_histogram_chart,
                                      result),
    }


def _box(bbox, color, tooltip, weight=AOI_WEIGHT, fill=0.10, dash=None,
         badge=None):
    return {"bbox": bbox, "color": color, "tooltip": tooltip,
            "weight": weight, "fillOpacity": fill, "dash": dash,
            "badge": badge}


def _hotspot_boxes(spec, hotspots):
    """One box per patch, with the gas's own tooltip wording and a rank badge."""
    boxes = []
    for rank, spot in enumerate(hotspots or [], start=1):
        lines = spec.hotspot_lines(spot, rank, len(hotspots))
        if spot.get("pixel_count"):
            extent = f"{spot['pixel_count']:.0f} cells above the cut"
            if spot.get("fill_pct") is not None:
                extent += f" — {spot['fill_pct']:.0f}% of this box"
            lines.append(extent)
        boxes.append(_box(
            {k: spot[k] for k in ("N", "S", "W", "E")},
            spec.hotspot_color, "<br>".join(lines),
            weight=HOTSPOT_WEIGHT,
            # Near-zero fill (not 0): unfilled rectangles only catch hover on
            # their stroke, so the AOI box underneath would steal the hover.
            fill=0.01, dash="6,4", badge=str(rank)))
    return boxes


def result_map(key, result, max_hotspots=None):
    """The map a gas page draws after a query: raster, AOI, hotspot patches.

    Hotspot boxes are a separate list so the client can slice them for its
    "how many to show" slider without re-requesting the map.
    """
    spec = modules(key)["mapview"].SPEC
    bbox = result["bbox"]
    hotspots = result.get("hotspots") or []
    if max_hotspots is not None:
        hotspots = hotspots[:max_hotspots]
    threshold = result.get(spec.threshold_key)

    tiles = []
    if result.get("context_tile_url"):
        tiles.append({"url": result["context_tile_url"],
                      "name": f"{spec.label} — surrounding area",
                      "opacity": 0.45, "show": False})
    if result.get("tile_url"):
        tiles.append({"url": result["tile_url"],
                      "name": f"{spec.label} — selected area",
                      "opacity": 0.85, "show": True})

    colorbar = None
    if result.get("vis_min") is not None and result.get("vis_max") is not None:
        colorbar = {"colors": list(spec.palette),
                    "vmin": float(result["vis_min"]),
                    "vmax": float(result["vis_max"]),
                    "caption": spec.colorbar_caption}

    return {
        "fit": bbox,
        "tiles": tiles,
        "boxes": [_box(bbox, result.get("level_color") or UNKNOWN_COLOR,
                       spec.aoi_tooltip(result))],
        "hotspotBoxes": _hotspot_boxes(spec, hotspots),
        "lines": [],
        "colorbar": colorbar,
        "hotspotLayerName": spec.hotspot_group_name(threshold),
    }


def compare_map(key, areas, selected=0, max_hotspots=None):
    """One map for two areas read against each other.

    Framed on the selected area, not both — two areas can be a continent
    apart. Follows shared/mapview.build_compare_map.
    """
    spec = modules(key)["mapview"].SPEC
    chosen = areas[selected]
    tiles = []
    if chosen["result"].get("tile_url"):
        tiles.append({"url": chosen["result"]["tile_url"],
                      "name": f"{spec.label} — {chosen['label']}",
                      "opacity": 0.85, "show": True})

    boxes, hotspot_boxes = [], []
    for area in areas:
        result = area["result"]
        if not result.get("bbox"):
            continue
        boxes.append(_box(result["bbox"],
                          result.get("level_color") or UNKNOWN_COLOR,
                          f"{area['label']} — {spec.aoi_tooltip(result)}"))
        spots = result.get("hotspots") or []
        if max_hotspots is not None:
            spots = spots[:max_hotspots]
        hotspot_boxes += _hotspot_boxes(spec, spots)

    chosen_result = chosen["result"]
    colorbar = None
    if (chosen_result.get("vis_min") is not None
            and chosen_result.get("vis_max") is not None):
        colorbar = {"colors": list(spec.palette),
                    "vmin": float(chosen_result["vis_min"]),
                    "vmax": float(chosen_result["vis_max"]),
                    "caption": f"{spec.colorbar_caption} — {chosen['label']}"}

    return {"fit": chosen_result["bbox"], "tiles": tiles, "boxes": boxes,
            "hotspotBoxes": hotspot_boxes, "lines": [], "colorbar": colorbar}


def preview_map(bbox, label="Selected area"):
    """Just the box, for before a query has been run."""
    return {"fit": bbox, "tiles": [],
            "boxes": [_box(bbox, "#1f77b4", label)],
            "hotspotBoxes": [], "lines": [], "colorbar": None}
