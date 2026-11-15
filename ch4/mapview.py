# ch4/mapview.py
# Folium map for the CH4 page. Base layers/boxes/colour bar come from
# shared/mapview.py; this file supplies CH4's palette and tooltip wording/units.

from shared.mapview import (MapSpec, build_result_map as _build_result_map,
                            build_compare_map as _build_compare_map)
from ch4.config import (CH4_PALETTE, HOTSPOT_COLOR, HOTSPOT_TEXT_COLOR, UNIT,
                        DEFAULT_HOTSPOT_REGIONS)


def _hotspot_group_name(threshold):
    cut = f" (>{threshold:.0f} {UNIT})" if threshold is not None else ""
    return f"Possible hotspots{cut}"


def _hotspot_lines(spot, rank, total):
    """Tooltip for one patch box. shared/mapview.py appends the extent line."""
    lines = [f"Hotspot {rank} of {total}"]
    if spot.get("mean_ch4_ppb") is not None:
        lines.append(f"Patch mean {spot['mean_ch4_ppb']:.1f} {UNIT}")
    if spot.get("max_ch4_ppb") is not None:
        lines.append(f"Patch max {spot['max_ch4_ppb']:.1f} {UNIT}")
    if spot.get("enhancement_ppb") is not None:
        lines.append(f"{spot['enhancement_ppb']:+.1f} {UNIT} vs background"
                     f" — {spot.get('level', 'Unknown')}")
    return lines


def _aoi_tooltip(result):
    """Tooltip on the AOI rectangle: the level, then the numbers behind it."""
    tooltip = f"{result.get('level', 'Unknown')}"
    if result.get("mean_ch4_ppb") is not None:
        tooltip += f" — mean {result['mean_ch4_ppb']:.1f} {UNIT}"
    if result.get("enhancement_ppb") is not None:
        tooltip += f" ({result['enhancement_ppb']:+.1f} {UNIT} vs background)"
    return tooltip


SPEC = MapSpec(
    label="CH4",
    palette=CH4_PALETTE,
    colorbar_caption=f"CH4 column mixing ratio ({UNIT})",
    hotspot_color=HOTSPOT_COLOR,
    badge_text_color=HOTSPOT_TEXT_COLOR,
    hotspot_group_name=_hotspot_group_name,
    hotspot_lines=_hotspot_lines,
    aoi_tooltip=_aoi_tooltip,
    threshold_key="hotspot_threshold_ppb",
)


def build_result_map(result, max_hotspots=DEFAULT_HOTSPOT_REGIONS):
    """Map with the CH4 raster overlay and the area highlighted by level."""
    return _build_result_map(result, SPEC, max_hotspots)


# ---- Compare view ----------------------------------------------------------
# Own spec: compare results carry no background, so patches are described
# relative to each area's own P80 instead.


def _compare_hotspot_group_name(threshold):
    cut = f" (> own P80, {threshold:.0f} {UNIT})" if threshold is not None else ""
    return f"Above P80{cut}"


def _compare_hotspot_lines(spot, rank, total):
    """Tooltip for one patch box, stated against the area's own P80 cut."""
    lines = [f"Hotspot {rank} of {total}"]
    if spot.get("mean_ch4_ppb") is not None:
        lines.append(f"Patch mean {spot['mean_ch4_ppb']:.1f} {UNIT}")
    if spot.get("max_ch4_ppb") is not None:
        lines.append(f"Patch max {spot['max_ch4_ppb']:.1f} {UNIT}")
    if spot.get("above_cut_ppb") is not None:
        lines.append(f"{spot['above_cut_ppb']:+.1f} {UNIT} above this area's "
                     "own P80 cut")
    return lines


def _compare_aoi_tooltip(result):
    """Tooltip on the AOI rectangle: the area's own numbers, nothing external."""
    parts = []
    if result.get("mean_ch4_ppb") is not None:
        parts.append(f"mean {result['mean_ch4_ppb']:.1f} {UNIT}")
    if (result.get("p10_ch4_ppb") is not None
            and result.get("p80_ch4_ppb") is not None):
        parts.append(f"P10-P80 {result['p10_ch4_ppb']:.0f}–"
                     f"{result['p80_ch4_ppb']:.0f} {UNIT}")
    return " · ".join(parts) or "No statistics for this area"


COMPARE_SPEC = MapSpec(
    label="CH4",
    palette=CH4_PALETTE,
    colorbar_caption=f"CH4 column mixing ratio ({UNIT})",
    hotspot_color=HOTSPOT_COLOR,
    badge_text_color=HOTSPOT_TEXT_COLOR,
    hotspot_group_name=_compare_hotspot_group_name,
    hotspot_lines=_compare_hotspot_lines,
    aoi_tooltip=_compare_aoi_tooltip,
    threshold_key="hotspot_threshold_ppb",
)


def build_compare_map(areas, selected=0, max_hotspots=DEFAULT_HOTSPOT_REGIONS):
    """One map for two areas compared: the selected one's raster, both
    outlined. No surrounding-area layer or background — each area is
    described on its own terms."""
    return _build_compare_map(areas, COMPARE_SPEC, selected, max_hotspots)
