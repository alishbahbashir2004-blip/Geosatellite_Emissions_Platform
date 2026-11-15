# co/mapview.py
# Folium map for the CO page. Base layers/boxes/colour bar come from
# shared/mapview.py; this file adds CO's palette, tooltip units, and loading.

from shared.mapview import (MapSpec, build_result_map as _build_result_map,
                            build_compare_map as _build_compare_map)
from co.config import (CO_PALETTE, HOTSPOT_COLOR, UNIT,
                       DEFAULT_HOTSPOT_REGIONS)

# Dark text on the badge, because the cyan is far too light to carry white.
HOTSPOT_TEXT_COLOR = "#062b33"


def _hotspot_group_name(threshold):
    cut = f" (>{threshold:.1f} {UNIT})" if threshold is not None else ""
    return f"Possible CO hotspots{cut}"


def _hotspot_lines(spot, rank, total):
    """Tooltip for one patch box. shared/mapview.py appends the extent line."""
    lines = [f"CO hotspot {rank} of {total}"]
    if spot.get("mean_co") is not None:
        lines.append(f"Patch mean {spot['mean_co']:.2f} {UNIT}")
    if spot.get("max_co") is not None:
        lines.append(f"Patch max {spot['max_co']:.2f} {UNIT}")
    if spot.get("enhancement_pct") is not None:
        # Percent first: it's the quantity the level is assigned on.
        absolute = spot.get("enhancement_co")
        tail = f" ({absolute:+.2f} {UNIT})" if absolute is not None else ""
        lines.append(f"{spot['enhancement_pct']:+.1f}% vs background{tail}"
                     f" — {spot.get('level', 'Unknown')}")
    return lines


def _aoi_tooltip(result):
    """Tooltip on the AOI rectangle: the level, then the numbers behind it."""
    tooltip = f"{result.get('level', 'Unknown')}"
    if result.get("mean_co") is not None:
        tooltip += f" — mean {result['mean_co']:.2f} {UNIT}"
    if result.get("enhancement_pct") is not None:
        tooltip += f" ({result['enhancement_pct']:+.1f}% vs background)"
    if result.get("loading_level"):
        tooltip += f" · regional loading {result['loading_level'].lower()}"
    return tooltip


SPEC = MapSpec(
    label="CO",
    palette=CO_PALETTE,
    colorbar_caption=f"CO total column ({UNIT})",
    hotspot_color=HOTSPOT_COLOR,
    badge_text_color=HOTSPOT_TEXT_COLOR,
    hotspot_group_name=_hotspot_group_name,
    hotspot_lines=_hotspot_lines,
    aoi_tooltip=_aoi_tooltip,
    threshold_key="hotspot_threshold_co",
)


def build_result_map(result, max_hotspots=DEFAULT_HOTSPOT_REGIONS):
    """Map with the CO raster overlay and the area highlighted by its level."""
    return _build_result_map(result, SPEC, max_hotspots)


# ---- Compare view ----------------------------------------------------------
# Own spec: compare results carry no background, so no enhancement, level, or
# loading verdict — patches are described vs. each area's own P80 instead.


def _compare_hotspot_group_name(threshold):
    cut = f" (> own P80, {threshold:.1f} {UNIT})" if threshold is not None else ""
    return f"Above P80{cut}"


def _compare_hotspot_lines(spot, rank, total):
    """Tooltip for one patch box, stated against the area's own P80 cut."""
    lines = [f"CO hotspot {rank} of {total}"]
    if spot.get("mean_co") is not None:
        lines.append(f"Patch mean {spot['mean_co']:.2f} {UNIT}")
    if spot.get("max_co") is not None:
        lines.append(f"Patch max {spot['max_co']:.2f} {UNIT}")
    if spot.get("above_cut_co") is not None:
        lines.append(f"{spot['above_cut_co']:+.2f} {UNIT} above this area's "
                     "own P80 cut")
    return lines


def _compare_aoi_tooltip(result):
    """Tooltip on the AOI rectangle: the area's own numbers, nothing external."""
    parts = []
    if result.get("mean_co") is not None:
        parts.append(f"mean {result['mean_co']:.2f} {UNIT}")
    if result.get("p10_co") is not None and result.get("p80_co") is not None:
        parts.append(f"P10-P80 {result['p10_co']:.2f}–{result['p80_co']:.2f} "
                     f"{UNIT}")
    return " · ".join(parts) or "No statistics for this area"


COMPARE_SPEC = MapSpec(
    label="CO",
    palette=CO_PALETTE,
    colorbar_caption=f"CO total column ({UNIT})",
    hotspot_color=HOTSPOT_COLOR,
    badge_text_color=HOTSPOT_TEXT_COLOR,
    hotspot_group_name=_compare_hotspot_group_name,
    hotspot_lines=_compare_hotspot_lines,
    aoi_tooltip=_compare_aoi_tooltip,
    threshold_key="hotspot_threshold_co",
)


def build_compare_map(areas, selected=0, max_hotspots=DEFAULT_HOTSPOT_REGIONS):
    """One map for two areas compared: the selected one's raster, both
    outlined. No surrounding-area layer or background — each area is
    described on its own terms."""
    return _build_compare_map(areas, COMPARE_SPEC, selected, max_hotspots)
