# no2/mapview.py
# The Folium map on the NO2 page; shared/mapview.py builds the map itself.
# Here: NO2's palette, layer names, and tooltip wording/units.

from shared.mapview import (MapSpec, build_result_map as _build_result_map,
                            build_compare_map as _build_compare_map)
from no2.config import (NO2_PALETTE, HOTSPOT_COLOR, HOTSPOT_TEXT_COLOR, UNIT,
                        DEFAULT_HOTSPOT_REGIONS)


def _hotspot_group_name(threshold):
    cut = f" (>{threshold:.1f} {UNIT})" if threshold is not None else ""
    return f"Possible NO2 hotspots{cut}"


def _hotspot_lines(spot, rank, total):
    """Tooltip for one patch box. shared/mapview.py appends the extent line."""
    lines = [f"NO2 hotspot {rank} of {total}"]
    if spot.get("mean_no2") is not None:
        lines.append(f"Patch mean {spot['mean_no2']:.1f} {UNIT}")
    if spot.get("max_no2") is not None:
        lines.append(f"Patch max {spot['max_no2']:.1f} {UNIT}")
    if spot.get("enhancement_pct") is not None:
        # Percent first: it's the quantity the level is assigned on.
        absolute = spot.get("enhancement_no2")
        tail = f" ({absolute:+.1f} {UNIT})" if absolute is not None else ""
        lines.append(f"{spot['enhancement_pct']:+.1f}% vs background{tail}"
                     f" — {spot.get('level', 'Unknown')}")
    return lines


def _aoi_tooltip(result):
    """Tooltip on the AOI rectangle: the level, then the numbers behind it."""
    tooltip = f"{result.get('level', 'Unknown')}"
    if result.get("mean_no2") is not None:
        tooltip += f" — mean {result['mean_no2']:.1f} {UNIT}"
    if result.get("enhancement_pct") is not None:
        tooltip += f" ({result['enhancement_pct']:+.1f}% vs background)"
    return tooltip


SPEC = MapSpec(
    label="NO2",
    palette=NO2_PALETTE,
    colorbar_caption=f"NO2 tropospheric column ({UNIT})",
    hotspot_color=HOTSPOT_COLOR,
    badge_text_color=HOTSPOT_TEXT_COLOR,
    hotspot_group_name=_hotspot_group_name,
    hotspot_lines=_hotspot_lines,
    aoi_tooltip=_aoi_tooltip,
    threshold_key="hotspot_threshold_no2",
)


def build_result_map(result, max_hotspots=DEFAULT_HOTSPOT_REGIONS):
    """Map with the NO2 raster overlay and the area highlighted by its level."""
    return _build_result_map(result, SPEC, max_hotspots)


# ---- Compare view ----------------------------------------------------------
# Own spec: compare results carry no background, so a patch here is hot
# relative to its own area's P80, and the tooltips say exactly that.


def _compare_hotspot_group_name(threshold):
    cut = f" (> own P80, {threshold:.1f} {UNIT})" if threshold is not None else ""
    return f"Above P80{cut}"


def _compare_hotspot_lines(spot, rank, total):
    """Tooltip for one patch box, stated against the area's own P80 cut."""
    lines = [f"Hotspot {rank} of {total}"]
    if spot.get("mean_no2") is not None:
        lines.append(f"Patch mean {spot['mean_no2']:.1f} {UNIT}")
    if spot.get("max_no2") is not None:
        lines.append(f"Patch max {spot['max_no2']:.1f} {UNIT}")
    if spot.get("above_cut_no2") is not None:
        lines.append(f"{spot['above_cut_no2']:+.1f} {UNIT} above this area's "
                     "own P80 cut")
    return lines


def _compare_aoi_tooltip(result):
    """Tooltip on the AOI rectangle: the area's own numbers, nothing external."""
    parts = []
    if result.get("mean_no2") is not None:
        parts.append(f"mean {result['mean_no2']:.1f} {UNIT}")
    if (result.get("p10_no2") is not None
            and result.get("p80_no2") is not None):
        parts.append(f"P10-P80 {result['p10_no2']:.1f}–"
                     f"{result['p80_no2']:.1f} {UNIT}")
    return " · ".join(parts) or "No statistics for this area"


COMPARE_SPEC = MapSpec(
    label="NO2",
    palette=NO2_PALETTE,
    colorbar_caption=f"NO2 tropospheric column ({UNIT})",
    hotspot_color=HOTSPOT_COLOR,
    badge_text_color=HOTSPOT_TEXT_COLOR,
    hotspot_group_name=_compare_hotspot_group_name,
    hotspot_lines=_compare_hotspot_lines,
    aoi_tooltip=_compare_aoi_tooltip,
    threshold_key="hotspot_threshold_no2",
)


def build_compare_map(areas, selected=0, max_hotspots=DEFAULT_HOTSPOT_REGIONS):
    """One map for two areas compared: the selected one's raster, both outlined.
    No background; hotspot boxes mark patches above each area's own P80."""
    return _build_compare_map(areas, COMPARE_SPEC, selected, max_hotspots)
