# co2/mapview.py
# CO2's maps: grid-cell view, ODIAC inventory, snapshot footprint — no single
# retrieval raster, so three styles. Tiles are pre-coloured server-side.

import branca.colormap as cm
import folium

from co2.config import SOURCES, ACCENT

ESRI_IMAGERY = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}")
GHG_ATTR = "NASA GHG Center / earth.gov"
AOI_COLOR = "#1f77b4"
BACKGROUND_COLOR = "#8e6bbf"
GRID_COLOR = "#ffffff"
FOOTPRINT_COLOR = "#ff6d00"

# Matched by eye to config.py's titiler colormap, so the bar means what the pixels mean.
MAGMA = ["#000004", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf"]


def _zoom_for(bbox):
    span = max(bbox["N"] - bbox["S"], bbox["E"] - bbox["W"])
    for limit, zoom in ((0.5, 10), (2, 8), (6, 6), (15, 5), (40, 4)):
        if span <= limit:
            return zoom
    return 3


def _base_map(bbox):
    center = [(bbox["N"] + bbox["S"]) / 2, (bbox["E"] + bbox["W"]) / 2]
    m = folium.Map(location=center, zoom_start=_zoom_for(bbox),
                   control_scale=True, tiles=None)
    folium.TileLayer(tiles=ESRI_IMAGERY,
                     attr="Esri, Maxar, Earthstar Geographics",
                     name="Satellite", overlay=False, control=True).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map", overlay=False,
                     control=True).add_to(m)
    return m


def _add_box(m, bbox, color, tooltip, dash=None, fill=0.08, weight=3):
    folium.Rectangle(
        bounds=[[bbox["S"], bbox["W"]], [bbox["N"], bbox["E"]]],
        color=color, weight=weight, opacity=0.95, dash_array=dash,
        fill=fill > 0, fill_color=color, fill_opacity=fill,
        tooltip=tooltip,
    ).add_to(m)


def _fit(m, bbox, pad=0.0):
    m.fit_bounds([[bbox["S"] - pad, bbox["W"] - pad],
                  [bbox["N"] + pad, bbox["E"] + pad]])
    folium.LayerControl(collapsed=False).add_to(m)
    return m


# ---------------------------------------------------------------------------
# 1. The resolution argument, drawn
# ---------------------------------------------------------------------------

def build_grid_map(bbox, source_key, adequacy, background_bbox=None,
                   label="Selected area"):
    """The AOI with the product's real grid cells ruled over it, snapped to
    the product's own cell origin (not the AOI's) so drawn cells match real ones."""
    m = _base_map(background_bbox or bbox)
    cell_lat, cell_lon = SOURCES[source_key]["cell_deg"]
    source_label = SOURCES[source_key]["label"]

    if background_bbox:
        _add_box(m, background_bbox, BACKGROUND_COLOR,
                 "Surrounding box used as the local background",
                 dash="8,6", fill=0.04)

    # Skip the lattice when it'd just be a solid block of lines (e.g. a
    # province against a 1 km inventory grid).
    extent = background_bbox or bbox
    span_lat = extent["N"] - extent["S"]
    span_lon = extent["E"] - extent["W"]
    lines = span_lat / cell_lat + span_lon / cell_lon
    if lines <= 120:
        group = folium.FeatureGroup(name=f"{source_label} grid cells",
                                    show=True)
        south = extent["S"] - (extent["S"] % cell_lat)
        west = extent["W"] - (extent["W"] % cell_lon)
        row = south
        while row < extent["N"] + cell_lat:
            folium.PolyLine([[row, extent["W"]], [row, extent["E"]]],
                            color=GRID_COLOR, weight=1, opacity=0.55).add_to(group)
            row += cell_lat
        column = west
        while column < extent["E"] + cell_lon:
            folium.PolyLine([[extent["S"], column], [extent["N"], column]],
                            color=GRID_COLOR, weight=1, opacity=0.55).add_to(group)
            column += cell_lon
        group.add_to(m)

    cells = adequacy["cells"]
    km_lat, km_lon = adequacy["cell_km"]
    _add_box(m, bbox, AOI_COLOR,
             f"{label} — spans {cells:.1f} {source_label} cells "
             f"(one cell is about {km_lat:.0f} x {km_lon:.0f} km here)",
             fill=0.12)
    return _fit(m, extent)


# ---------------------------------------------------------------------------
# 2. Where the CO2 is emitted
# ---------------------------------------------------------------------------

def build_inventory_map(result):
    """The ODIAC 1 km emissions raster under the AOI outline — a modelled
    allocation, not an observed plume."""
    bbox = result["bbox"]
    m = _base_map(bbox)
    folium.TileLayer(
        tiles=result["tile_url"], attr=GHG_ATTR,
        name="Fossil-fuel CO2 emissions (ODIAC, 1 km)",
        overlay=True, control=True, opacity=0.80, show=True,
    ).add_to(m)

    latest = result["latest"]
    _add_box(m, bbox, AOI_COLOR,
             f"{result['label']} — "
             f"{latest['mean_tco2_per_km2_month']:,.0f} t CO2/km²/month "
             f"in {latest['date'][:7]}", fill=0.0)
    _add_class_legend(m, result["classes"])
    return _fit(m, bbox)


def _add_class_legend(m, classes):
    """Equal-width swatch legend for ODIAC's class intervals (not a
    continuous bar — classes step ~3x each, which would squeeze the lower ones)."""
    swatches = "".join(
        f"<div style='flex:1;text-align:center;'>"
        f"<div style='height:12px;background:{colour};'></div>"
        f"<div style='font-size:9px;color:#333;padding-top:2px;'>"
        f"{('>' + format(low, ',.0f')) if high is None else format(high, ',.0f')}"
        f"</div></div>"
        for low, high, colour in classes)
    html = (
        "<div style='position:fixed;bottom:18px;left:12px;z-index:9999;"
        "background:rgba(255,255,255,0.93);padding:7px 9px;border-radius:4px;"
        "box-shadow:0 1px 4px rgba(0,0,0,0.3);font-family:sans-serif;"
        "width:330px;'>"
        "<div style='font-size:10px;font-weight:600;color:#222;"
        "padding-bottom:4px;'>Fossil-fuel CO2 — tonnes per 1 km cell per "
        "month</div>"
        f"<div style='display:flex;gap:1px;'>{swatches}</div>"
        "<div style='font-size:9px;color:#666;padding-top:4px;'>"
        "Uncoloured land emits nothing at all in this inventory — that is "
        "missing data, not zero.</div>"
        "</div>")
    m.get_root().html.add_child(folium.Element(html))


# ---------------------------------------------------------------------------
# 3. Real soundings, where the satellite was aimed
# ---------------------------------------------------------------------------

def build_snapshot_map(result):
    """One targeted snapshot, with the footprint it actually covered — rarely
    matching the AOI since the satellite was aimed at a target, not the box."""
    footprint = result["footprint"]
    bbox = result["bbox"]
    m = _base_map(footprint)

    folium.TileLayer(
        tiles=result["tile_url"], attr=GHG_ATTR,
        name=f"XCO2 soundings — {result['chosen']['date']}",
        overlay=True, control=True, opacity=0.85, show=True,
    ).add_to(m)

    stats = result["stats"]
    _add_box(m, footprint, FOOTPRINT_COLOR,
             f"Snapshot footprint — {result['covered_km2']:,.0f} km² "
             f"measured, mean {stats['mean']:.2f} ppm, "
             f"spread {result['spread']:.2f} ppm",
             dash="8,6", fill=0.0, weight=2)
    _add_box(m, bbox, AOI_COLOR, f"{result['label']} (your selection)",
             fill=0.0)

    low, high = result["rescale"]
    cm.LinearColormap(colors=MAGMA, vmin=float(low), vmax=float(high),
                      caption="XCO2 (ppm)").add_to(m)

    union = {"N": max(footprint["N"], bbox["N"]),
             "S": min(footprint["S"], bbox["S"]),
             "W": min(footprint["W"], bbox["W"]),
             "E": max(footprint["E"], bbox["E"])}
    return _fit(m, union)


# ---------------------------------------------------------------------------
# 4. What the NO2 inference is actually looking at
# ---------------------------------------------------------------------------

def build_inferred_map(result):
    """The two boxes the NO2 enhancement was measured between. No raster —
    this is a difference between two areas, not something to read CO2 off."""
    bbox = result["bbox"]
    background = result["background_bbox"]
    m = _base_map(background)
    _add_box(m, background, BACKGROUND_COLOR,
             f"Local background — NO2 {result['no2_background']:.1f} µmol/m²",
             dash="8,6", fill=0.04)
    _add_box(m, bbox, ACCENT,
             f"{result['label']} — NO2 {result['no2_aoi']:.1f} µmol/m² "
             f"({result['no2_delta']:+.1f} vs background)", fill=0.12)
    return _fit(m, background)
