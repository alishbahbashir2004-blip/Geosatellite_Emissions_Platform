# shared/mapview.py
# The Folium map every gas page draws: base layers, AOI rectangle, hotspot
# boxes, and raster colour bar. Per-gas naming/tooltips arrive as a MapSpec;
# tooltips are callables on it, so this module never learns units.

import folium
import branca.colormap as cm

from dataclasses import dataclass
from typing import Callable

EE_ATTR = "Map data &copy; Google Earth Engine / Copernicus Sentinel-5P"

ESRI_IMAGERY = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

UNKNOWN_COLOR = "#607d8b"


@dataclass(frozen=True)
class MapSpec:
    """Everything about the map that is a statement about one gas.
    `hotspot_lines`/`aoi_tooltip` read the gas's own result keys/units."""
    label: str                  # "CH4" — used in the overlay layer names
    palette: list               # the raster's colour ramp
    colorbar_caption: str       # caption under the colour bar
    hotspot_color: str          # patch box outline, a hue the palette avoids
    badge_text_color: str       # text on the rank badge, for contrast
    hotspot_group_name: Callable[[object], str]   # threshold -> layer name
    hotspot_lines: Callable[[dict, int, int], list]  # spot, rank, total
    aoi_tooltip: Callable[[dict], str]
    threshold_key: str          # result key holding the cut the boxes use


def _zoom_for(bbox):
    """Rough zoom level from the size of the box, used before fit_bounds."""
    span = max(bbox["N"] - bbox["S"], bbox["E"] - bbox["W"])
    for limit, zoom in ((0.5, 10), (2, 8), (6, 6), (15, 5), (40, 4)):
        if span <= limit:
            return zoom
    return 3


def _base_map(bbox):
    center = [(bbox["N"] + bbox["S"]) / 2, (bbox["E"] + bbox["W"]) / 2]
    m = folium.Map(location=center, zoom_start=_zoom_for(bbox),
                   control_scale=True, tiles=None)
    folium.TileLayer(
        tiles=ESRI_IMAGERY, attr="Esri, Maxar, Earthstar Geographics",
        name="Satellite", overlay=False, control=True,
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map", overlay=False,
                     control=True).add_to(m)
    return m


def _add_highlight(m, bbox, color, tooltip, fill_opacity=0.10):
    folium.Rectangle(
        bounds=[[bbox["S"], bbox["W"]], [bbox["N"], bbox["E"]]],
        color=color, weight=3, opacity=0.95,
        fill=True, fill_color=color, fill_opacity=fill_opacity,
        tooltip=tooltip,
    ).add_to(m)


def _add_hotspot_boxes(m, spec, hotspots, threshold, name=None):
    """One box per contiguous above-threshold patch, on its own toggle layer.
    Hotspots arrive ranked hottest-first, so labels read 1..n."""
    if not hotspots:
        return
    group = folium.FeatureGroup(name=name or spec.hotspot_group_name(threshold),
                                show=True)

    for rank, spot in enumerate(hotspots, start=1):
        lines = spec.hotspot_lines(spot, rank, len(hotspots))
        if spot.get("pixel_count"):
            extent = f"{spot['pixel_count']:.0f} cells above the cut"
            if spot.get("fill_pct") is not None:
                extent += f" — {spot['fill_pct']:.0f}% of this box"
            lines.append(extent)

        # Near-zero fill (not fill=False): an unfilled box only catches hover on
        # its stroke, letting the filled AOI rectangle underneath steal the hover.
        folium.Rectangle(
            bounds=[[spot["S"], spot["W"]], [spot["N"], spot["E"]]],
            color=spec.hotspot_color, weight=2.5, opacity=0.95,
            fill=True, fill_color=spec.hotspot_color, fill_opacity=0.01,
            dash_array="6,4",
            tooltip=folium.Tooltip("<br>".join(lines), sticky=True),
        ).add_to(group)

        # Rank pinned to the box corner, so boxes stay distinguishable unhovered.
        folium.Marker(
            location=[spot["N"], spot["W"]], interactive=False,
            icon=folium.DivIcon(html=(
                '<div style="font:600 11px/1 sans-serif;'
                f'color:{spec.badge_text_color};'
                f'background:{spec.hotspot_color};border-radius:3px;'
                'padding:2px 5px;display:inline-block;white-space:nowrap;'
                'pointer-events:none;">'  # else the badge eats hover at the box corner
                f'{rank}</div>'
            )),
        ).add_to(group)

    group.add_to(m)


def build_preview_map(bbox, label="Selected area"):
    """Map with just the selected area outlined. Unused since the idle map
    slot became the globe in globeview.py; kept in case it's reinstated."""
    m = _base_map(bbox)
    _add_highlight(m, bbox, "#ffffff", label, fill_opacity=0.05)
    m.fit_bounds([[bbox["S"], bbox["W"]], [bbox["N"], bbox["E"]]])
    folium.LayerControl(collapsed=True).add_to(m)
    return m


def build_result_map(result, spec, max_hotspots):
    """Map with the gas's raster overlay and the area highlighted by level.
    `max_hotspots` trims the drawn boxes without another EE call."""
    bbox = result["bbox"]
    m = _base_map(bbox)

    # Wider context raster, off by default, for comparing AOI to surroundings.
    if result.get("context_tile_url"):
        folium.TileLayer(
            tiles=result["context_tile_url"], attr=EE_ATTR,
            name=f"{spec.label} — surrounding area", overlay=True,
            control=True, opacity=0.45, show=False,
        ).add_to(m)

    if result.get("tile_url"):
        folium.TileLayer(
            tiles=result["tile_url"], attr=EE_ATTR,
            name=f"{spec.label} — selected area", overlay=True, control=True,
            opacity=0.85, show=True,
        ).add_to(m)

    _add_highlight(m, bbox, result.get("level_color") or UNKNOWN_COLOR,
                   spec.aoi_tooltip(result))

    # On top of the AOI outline: the sub-regions carrying the hot tail.
    hotspots = result.get("hotspots") or []
    if max_hotspots is not None:
        hotspots = hotspots[:max_hotspots]
    _add_hotspot_boxes(m, spec, hotspots, result.get(spec.threshold_key))

    # Colour bar for the raster stretch.
    vmin, vmax = result.get("vis_min"), result.get("vis_max")
    if vmin is not None and vmax is not None:
        cm.LinearColormap(
            colors=spec.palette, vmin=float(vmin), vmax=float(vmax),
            caption=spec.colorbar_caption,
        ).add_to(m)

    m.fit_bounds([[bbox["S"], bbox["W"]], [bbox["N"], bbox["E"]]])
    folium.LayerControl(collapsed=False).add_to(m)
    return m


def build_compare_map(areas, spec, selected=0, max_hotspots=None):
    """One map for two or more areas measured against each other.
    `areas` is [{"label", "result"}, ...]; `selected` indexes the drawn raster.
    Unlike build_result_map: only one raster shown at a time (areas are each
    other's reference); every area's outline/hotspots are still drawn."""
    chosen = areas[selected]
    bbox = chosen["result"]["bbox"]
    m = _base_map(bbox)

    if chosen["result"].get("tile_url"):
        folium.TileLayer(
            tiles=chosen["result"]["tile_url"], attr=EE_ATTR,
            name=f"{spec.label} — {chosen['label']}", overlay=True,
            control=True, opacity=0.85, show=True,
        ).add_to(m)

    for area in areas:
        result = area["result"]
        if not result.get("bbox"):
            continue
        _add_highlight(
            m, result["bbox"],
            result.get("level_color") or UNKNOWN_COLOR,
            f"{area['label']} — {spec.aoi_tooltip(result)}",
        )
        hotspots = result.get("hotspots") or []
        if max_hotspots is not None:
            hotspots = hotspots[:max_hotspots]
        threshold = result.get(spec.threshold_key)
        _add_hotspot_boxes(
            m, spec, hotspots, threshold,
            name=f"{area['label']} — {spec.hotspot_group_name(threshold)}",
        )

    # Colour bar for the raster on screen, captioned with whose it is.
    vmin, vmax = chosen["result"].get("vis_min"), chosen["result"].get("vis_max")
    if vmin is not None and vmax is not None:
        cm.LinearColormap(
            colors=spec.palette, vmin=float(vmin), vmax=float(vmax),
            caption=f"{spec.colorbar_caption} — {chosen['label']}",
        ).add_to(m)

    # Framed on the selected area only: areas can be a continent apart.
    m.fit_bounds([[bbox["S"], bbox["W"]], [bbox["N"], bbox["E"]]])
    folium.LayerControl(collapsed=False).add_to(m)
    return m
