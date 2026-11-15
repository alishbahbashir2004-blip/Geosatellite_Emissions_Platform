# ch4/backend.py
# LangGraph workflow: pulls Sentinel-5P CH4 (ppb), compares it to a padded
# background box, returns map tiles/numbers/chart data. Shared structure in shared/.

import ee
from datetime import datetime, timedelta
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from shared.earthengine import init as ee_init, tile_url as _tile_url
from shared.geo import resolve_bbox, context_bbox
from shared.pipeline import daily_stats, hotspot_regions
from shared.stats import histogram_rows, box_stats
from shared.levels import classify
from ch4.config import (
    CH4_ASSET, CH4_BAND, REDUCE_SCALE, BACKGROUND_SCALE, HISTOGRAM_BUCKETS,
    EMISSION_LEVELS, CH4_PALETTE, CH4_VIS_FALLBACK, MIN_VIS_SPREAD,
    MAX_HOTSPOT_REGIONS,
)

ee_init()

# Re-exported so the CH4 page can offer a location without importing shared
# directly, mirroring how the CO page imports resolve_bbox from its backend.
__all__ = ["run_pipeline", "run_area_pipeline", "resolve_bbox",
           "classify_enhancement", "MethaneState", "AreaState"]


def classify_enhancement(enhancement_ppb: Optional[float]):
    """Map a CH4 enhancement (ppb above local background) to a level; absolute
    ppb, not percent — see EMISSION_LEVELS."""
    return classify(enhancement_ppb, EMISSION_LEVELS)


# ---- Workflow state ---------------------------------------------------------
class MethaneState(TypedDict):
    region_name: Optional[str]
    city_name: Optional[str]
    N: Optional[float]
    S: Optional[float]
    W: Optional[float]
    E: Optional[float]
    date_start: str
    date_end: str
    mean_ch4_ppb: Optional[float]
    pass_count: Optional[int]
    error: Optional[str]
    # --- map / classification outputs ---
    bbox: Optional[dict]              # {N, S, W, E} of the area queried
    background_ch4_ppb: Optional[float]
    enhancement_ppb: Optional[float]  # mean - background
    # --- the same comparison with both tails trimmed off each side ---
    core_mean_ch4_ppb: Optional[float]      # mean of AOI pixels in P10-P80
    bg_p10_ch4_ppb: Optional[float]         # background's own percentiles,
    bg_p80_ch4_ppb: Optional[float]         #   measured over the wider box
    bg_core_mean_ch4_ppb: Optional[float]   # mean of background P10-P80
    bg_histogram: Optional[list]            # [{value,start,end,count}] over
                                            #   the whole background region
    bg_box_stats: Optional[dict]            # its min, max and P10/P80 cuts
    core_enhancement_ppb: Optional[float]   # core mean - background core mean
    core_level: Optional[str]               # same scale as `level`
    level: Optional[str]              # "Low" / "Moderate" / "High" / ...
    level_color: Optional[str]        # hex colour for the AOI highlight
    # --- hot end of the box, where a localised plume shows up ---
    hotspot_enhancement_ppb: Optional[float]  # P80 - background
    hotspot_level: Optional[str]              # same scale as `level`
    peak_enhancement_ppb: Optional[float]     # max value - background
    hotspot_threshold_ppb: Optional[float]    # P80, the cut the boxes use
    hotspot_region_count: Optional[int]       # patches found, before the
                                              # MAX_HOTSPOT_REGIONS cap
    hotspot_error: Optional[str]              # why the boxes are missing, if
                                              # the segmentation itself failed
    hotspots: Optional[list]                  # [{N,S,W,E,mean_ch4_ppb,max_ch4_ppb,
                                              #   pixel_count,enhancement_ppb,level,
                                              #   level_color}], above-P80, hottest first
    # --- pixel distribution of the composite, for the histogram + box plot ---
    histogram: Optional[list]         # [{value, start, end, count}] per bucket
    box_stats: Optional[dict]         # min, max and the P10-P80 quantiles
    tile_url: Optional[str]           # CH4 raster clipped to the AOI
    context_tile_url: Optional[str]   # CH4 raster over the surrounding area
    vis_min: Optional[float]
    vis_max: Optional[float]
    series: Optional[list]            # [{date, ch4}] daily means, for the chart
    # --- spread of the period-mean image across the pixels of the box ---
    min_ch4_ppb: Optional[float]
    max_ch4_ppb: Optional[float]
    median_ch4_ppb: Optional[float]
    p10_ch4_ppb: Optional[float]
    p80_ch4_ppb: Optional[float]
    # --- per-day pixel availability, for the availability chart ---
    availability: Optional[list]      # [{date, sample_count, valid_count,
                                      #   no_data_count}]


def _spread_reducer():
    """Mean, min/max, percentiles and histogram combined into one reducer,
    so every AOI-wide number comes back in a single round trip."""
    return (ee.Reducer.mean()
            .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.percentile([2, 10, 25, 50, 75, 80, 98]),
                     sharedInputs=True)
            .combine(reducer2=ee.Reducer.histogram(maxBuckets=HISTOGRAM_BUCKETS),
                     sharedInputs=True))


def _core_band(image, low, high):
    """Band with everything outside P10-P80 masked, so the mean isn't skewed
    by a partly clouded pass (cold tail) or a plume (hot tail)."""
    if low is None or high is None:
        return None
    band = image.select(CH4_BAND)
    return band.updateMask(band.gte(low).And(band.lte(high)))


def _vis_range(p2, p98):
    """Colour stretch: the AOI's own percentiles, or the fallback if degenerate."""
    if p2 is not None and p98 is not None and p98 - p2 > MIN_VIS_SPREAD:
        return float(p2), float(p98)
    return CH4_VIS_FALLBACK


def _describe_patch(background):
    """Methane fields for each hotspot patch, for shared.pipeline.hotspot_regions
    (which ranks patches but doesn't know their unit)."""
    def describe(patch_mean, patch_max):
        enhancement = None if background is None else patch_mean - background
        level, level_color = classify_enhancement(enhancement)
        return {
            "mean_ch4_ppb": patch_mean,
            "max_ch4_ppb": patch_max,
            "enhancement_ppb": enhancement,
            "level": level,
            "level_color": level_color,
        }
    return describe


# ---- Node: fetch CH4 concentration from Earth Engine ------------------------
def fetch_ch4(state: MethaneState) -> MethaneState:
    bbox, err = resolve_bbox(
        state.get("region_name"), state.get("city_name"),
        state.get("N"), state.get("S"), state.get("W"), state.get("E"),
    )
    if err:
        return {**state, "error": err}

    n, s, w, e = bbox["N"], bbox["S"], bbox["W"], bbox["E"]
    aoi = ee.Geometry.Rectangle([w, s, e, n])

    ctx = context_bbox(bbox)
    context_aoi = ee.Geometry.Rectangle([ctx["W"], ctx["S"], ctx["E"], ctx["N"]])

    # Validate and normalize dates (EE's end date is exclusive)
    try:
        start_dt = datetime.strptime(state["date_start"], "%Y-%m-%d")
        end_dt = datetime.strptime(state["date_end"], "%Y-%m-%d")
    except Exception:
        return {**state, "error": "date_start/date_end must be YYYY-MM-DD."}

    if start_dt > end_dt:
        return {**state, "error": "date_start must be <= date_end."}
    if start_dt == end_dt:
        end_dt += timedelta(days=1)

    date_start_str = start_dt.strftime("%Y-%m-%d")
    date_end_str = end_dt.strftime("%Y-%m-%d")

    base = (
        ee.ImageCollection(CH4_ASSET)
        .filterDate(date_start_str, date_end_str)
        .select(CH4_BAND)
    )
    collection = base.filterBounds(aoi)

    try:
        pass_count = collection.size().getInfo()
    except Exception as exc:
        return {**state,
                "error": f"Earth Engine error getting collection size: {exc}"}

    if pass_count == 0:
        return {**state, "bbox": bbox,
                "error": "No satellite passes found for this region/date range."}

    mean_image = collection.mean()

    # One round trip for mean, spread stats, and the 2nd/98th percentiles
    # used for the raster colour stretch.
    try:
        stats = mean_image.reduceRegion(
            reducer=_spread_reducer(), geometry=aoi, scale=REDUCE_SCALE,
            maxPixels=1e9, bestEffort=True,
        ).getInfo()
    except Exception as exc:
        return {**state, "bbox": bbox,
                "error": f"Earth Engine error reducing region: {exc}"}

    def stat(name):
        """Pull one reducer output; they all come back band-name prefixed."""
        return stats.get(f"{CH4_BAND}_{name}")

    mean_ch4, p2, p98 = stat("mean"), stat("p2"), stat("p98")

    # Local background: same period, surrounding area, using passes over the
    # wider box so the context layer is fully covered. Non-fatal if it fails.
    context_mean_image = base.filterBounds(context_aoi).mean()
    background = bg_p10 = bg_p80 = None
    bg_histogram = bg_box = None
    try:
        bg_stats = context_mean_image.reduceRegion(
            reducer=(ee.Reducer.mean()
                     .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
                     .combine(reducer2=ee.Reducer.percentile([10, 80]),
                              sharedInputs=True)
                     .combine(reducer2=ee.Reducer.histogram(
                         maxBuckets=HISTOGRAM_BUCKETS), sharedInputs=True)),
            geometry=context_aoi,
            scale=BACKGROUND_SCALE, maxPixels=1e9, bestEffort=True,
        ).getInfo()
        background = bg_stats.get(f"{CH4_BAND}_mean")
        bg_p10 = bg_stats.get(f"{CH4_BAND}_p10")
        bg_p80 = bg_stats.get(f"{CH4_BAND}_p80")
        # Whole background distribution, not just the P10-P80 slice, so this
        # chart bands the same range as the AOI chart and the two compare.
        bg_histogram = histogram_rows(bg_stats.get(f"{CH4_BAND}_histogram"))
        bg_box = box_stats(bg_histogram, {
            "min": bg_stats.get(f"{CH4_BAND}_min"), "p10": bg_p10,
            "p80": bg_p80, "max": bg_stats.get(f"{CH4_BAND}_max"),
        })
    except Exception:
        background = bg_p10 = bg_p80 = None
        bg_histogram = bg_box = None

    # Mean of pixels inside P10-P80, AOI and background each on their own
    # percentiles; needs a second pass since the cuts aren't known until above.
    core_mean = bg_core_mean = None
    try:
        wanted = {}
        aoi_core = _core_band(mean_image, stat("p10"), stat("p80"))
        bg_core = _core_band(context_mean_image, bg_p10, bg_p80)
        if aoi_core is not None:
            wanted["aoi"] = aoi_core.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=aoi, scale=REDUCE_SCALE,
                maxPixels=1e9, bestEffort=True)
        if bg_core is not None:
            wanted["bg"] = bg_core.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=context_aoi,
                scale=BACKGROUND_SCALE, maxPixels=1e9, bestEffort=True)
        if wanted:
            got = ee.Dictionary(wanted).getInfo()
            core_mean = (got.get("aoi") or {}).get(CH4_BAND)
            bg_core_mean = (got.get("bg") or {}).get(CH4_BAND)
    except Exception:
        core_mean = bg_core_mean = None

    # The headline comparison with both tails taken off each side.
    core_enhancement = None
    if core_mean is not None and bg_core_mean is not None:
        core_enhancement = core_mean - bg_core_mean
    core_level, _ = classify_enhancement(core_enhancement)

    enhancement = None
    if mean_ch4 is not None and background is not None:
        enhancement = mean_ch4 - background
    level, level_color = classify_enhancement(enhancement)

    # Same comparison at the hot end: P80 and peak vs. background, since a
    # small plume barely moves the area mean.
    def above_background(value):
        if value is None or background is None:
            return None
        return value - background

    hotspot_enhancement = above_background(stat("p80"))
    peak_enhancement = above_background(stat("max"))
    hotspot_level, _ = classify_enhancement(hotspot_enhancement)

    # Non-fatal if this fails (page stands without the boxes), but the error
    # is kept so a missing overlay isn't confused with "no hotspots found".
    hotspot_error = None
    try:
        hotspots, hotspot_count = hotspot_regions(
            mean_image, aoi, bbox, stat("p80"), REDUCE_SCALE,
            MAX_HOTSPOT_REGIONS, _describe_patch(background))
    except Exception as exc:
        hotspots, hotspot_count = None, None
        hotspot_error = f"Hotspot segmentation failed: {exc}"

    # Pixel distribution of the composite: histogram chart reads the rows,
    # box plot reads the summary.
    histogram = histogram_rows(stats.get(f"{CH4_BAND}_histogram"))
    box = box_stats(histogram, {
        "min": stat("min"), "p10": stat("p10"), "p25": stat("p25"),
        "p50": stat("p50"), "p75": stat("p75"), "p80": stat("p80"),
        "max": stat("max"),
    })

    # Colour stretch: prefer the AOI's own percentiles, fall back to a
    # sensible global range if they're missing or degenerate.
    vis_min, vis_max = _vis_range(p2, p98)

    vis = {"min": vis_min, "max": vis_max, "palette": CH4_PALETTE}
    try:
        tiles = _tile_url(mean_image.clip(aoi), vis)
        context_tiles = _tile_url(context_mean_image.clip(context_aoi), vis)
    except Exception:
        tiles = context_tiles = None

    # Chart data. Also non-fatal: the numbers and map still stand without it.
    try:
        series, availability = daily_stats(collection, aoi, CH4_BAND,
                                           REDUCE_SCALE, "ch4")
    except Exception:
        series, availability = None, None

    return {
        **state,
        "mean_ch4_ppb": mean_ch4,
        "pass_count": pass_count,
        "error": None,
        "bbox": bbox,
        "background_ch4_ppb": background,
        "enhancement_ppb": enhancement,
        "level": level,
        "level_color": level_color,
        "tile_url": tiles,
        "context_tile_url": context_tiles,
        "vis_min": vis_min,
        "vis_max": vis_max,
        "series": series,
        "min_ch4_ppb": stat("min"),
        "max_ch4_ppb": stat("max"),
        "median_ch4_ppb": stat("p50"),
        "p10_ch4_ppb": stat("p10"),
        "p80_ch4_ppb": stat("p80"),
        "core_mean_ch4_ppb": core_mean,
        "bg_p10_ch4_ppb": bg_p10,
        "bg_p80_ch4_ppb": bg_p80,
        "bg_core_mean_ch4_ppb": bg_core_mean,
        "bg_histogram": bg_histogram,
        "bg_box_stats": bg_box,
        "core_enhancement_ppb": core_enhancement,
        "core_level": core_level,
        "hotspot_enhancement_ppb": hotspot_enhancement,
        "hotspot_level": hotspot_level,
        "peak_enhancement_ppb": peak_enhancement,
        "hotspot_threshold_ppb": stat("p80"),
        "hotspots": hotspots,
        "hotspot_region_count": hotspot_count,
        "hotspot_error": hotspot_error,
        "histogram": histogram,
        "box_stats": box,
        "availability": availability,
    }


# ---- Build the graph (single node for now; more steps come later) -----------
graph = StateGraph(MethaneState)
graph.add_node("fetch_ch4", fetch_ch4)
graph.set_entry_point("fetch_ch4")
graph.add_edge("fetch_ch4", END)
workflow = graph.compile()


# ---- Convenience wrapper for the frontend -----------------------------------
def run_pipeline(region_name=None, city_name=None, N=None, S=None, W=None,
                 E=None, date_start="", date_end=""):
    """Run the CH4 pipeline and return the finished state dict."""
    initial_state: MethaneState = {
        "region_name": region_name, "city_name": city_name,
        "N": N, "S": S, "W": W, "E": E,
        "date_start": date_start, "date_end": date_end,
        "mean_ch4_ppb": None, "pass_count": None, "error": None,
        "bbox": None, "background_ch4_ppb": None, "enhancement_ppb": None,
        "level": None, "level_color": None, "tile_url": None,
        "context_tile_url": None, "vis_min": None, "vis_max": None,
        "series": None, "min_ch4_ppb": None, "max_ch4_ppb": None,
        "median_ch4_ppb": None,
        "core_mean_ch4_ppb": None, "bg_p10_ch4_ppb": None,
        "bg_p80_ch4_ppb": None, "bg_core_mean_ch4_ppb": None,
        "bg_histogram": None, "bg_box_stats": None,
        "core_enhancement_ppb": None, "core_level": None,
        "p10_ch4_ppb": None, "p80_ch4_ppb": None,
        "hotspot_enhancement_ppb": None, "hotspot_level": None,
        "peak_enhancement_ppb": None, "availability": None,
        "hotspot_threshold_ppb": None, "hotspots": None,
        "hotspot_region_count": None, "hotspot_error": None,
        "histogram": None, "box_stats": None,
    }
    return workflow.invoke(initial_state)


# ---- The background-free pipeline --------------------------------------------
# Compare view: one AOI alone — no background or enhancement/level. Also
# lighter: no context tiles or series (compare page has no charts).


class AreaState(TypedDict):
    # --- inputs ---
    region_name: Optional[str]
    city_name: Optional[str]
    N: Optional[float]
    S: Optional[float]
    W: Optional[float]
    E: Optional[float]
    date_start: str
    date_end: str
    # --- headline ---
    mean_ch4_ppb: Optional[float]
    pass_count: Optional[int]
    error: Optional[str]
    bbox: Optional[dict]               # {N, S, W, E} of the area queried
    # --- spread of the period-mean image across the pixels of the box ---
    min_ch4_ppb: Optional[float]
    max_ch4_ppb: Optional[float]
    median_ch4_ppb: Optional[float]
    p10_ch4_ppb: Optional[float]
    p80_ch4_ppb: Optional[float]
    core_mean_ch4_ppb: Optional[float]     # mean of the pixels inside P10-P80
    # --- hot end of the box, measured against the box's own P80 ---
    hotspot_threshold_ppb: Optional[float]   # the AOI's own P80: the only cut
    hotspot_region_count: Optional[int]      # patches found, before the cap
    hotspot_error: Optional[str]
    hotspots: Optional[list]                 # [{N,S,W,E,mean_ch4_ppb,max_ch4_ppb,
                                             #   pixel_count,fill_pct,above_cut_ppb}],
                                             #   hottest first
    # --- pixel distribution and the raster ---
    histogram: Optional[list]
    box_stats: Optional[dict]
    tile_url: Optional[str]
    vis_min: Optional[float]
    vis_max: Optional[float]
    # --- per-day pixel availability, for the availability chart ---
    availability: Optional[list]           # [{date, sample_count, valid_count,
                                           #   no_data_count}]


def _describe_patch_above_cut(cut):
    """Patch fields with no background: how far above the AOI's own P80 it
    sits. No level — levels band an enhancement over a background that
    doesn't exist here."""
    def describe(patch_mean, patch_max):
        return {
            "mean_ch4_ppb": patch_mean,
            "max_ch4_ppb": patch_max,
            "above_cut_ppb": None if cut is None else patch_mean - cut,
        }
    return describe


def fetch_area(state: AreaState) -> AreaState:
    bbox, err = resolve_bbox(
        state.get("region_name"), state.get("city_name"),
        state.get("N"), state.get("S"), state.get("W"), state.get("E"),
    )
    if err:
        return {**state, "error": err}

    n, s, w, e = bbox["N"], bbox["S"], bbox["W"], bbox["E"]
    aoi = ee.Geometry.Rectangle([w, s, e, n])

    # Validate and normalize dates (EE's end date is exclusive)
    try:
        start_dt = datetime.strptime(state["date_start"], "%Y-%m-%d")
        end_dt = datetime.strptime(state["date_end"], "%Y-%m-%d")
    except Exception:
        return {**state, "error": "date_start/date_end must be YYYY-MM-DD."}

    if start_dt > end_dt:
        return {**state, "error": "date_start must be <= date_end."}
    if start_dt == end_dt:
        end_dt += timedelta(days=1)

    collection = (
        ee.ImageCollection(CH4_ASSET)
        .filterDate(start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
        .select(CH4_BAND)
        .filterBounds(aoi)
    )

    try:
        pass_count = collection.size().getInfo()
    except Exception as exc:
        return {**state,
                "error": f"Earth Engine error getting collection size: {exc}"}

    if pass_count == 0:
        return {**state, "bbox": bbox,
                "error": "No satellite passes found for this region/date range."}

    mean_image = collection.mean()

    try:
        stats = mean_image.reduceRegion(
            reducer=_spread_reducer(), geometry=aoi, scale=REDUCE_SCALE,
            maxPixels=1e9, bestEffort=True,
        ).getInfo()
    except Exception as exc:
        return {**state, "bbox": bbox,
                "error": f"Earth Engine error reducing region: {exc}"}

    def stat(name):
        """Pull one reducer output; they all come back band-name prefixed."""
        return stats.get(f"{CH4_BAND}_{name}")

    mean_ch4 = stat("mean")
    if mean_ch4 is None:
        return {**state, "bbox": bbox, "pass_count": pass_count,
                "error": "No CH4 pixels survived masking over this area and "
                         "period. Try a longer date range."}

    # Mean of pixels inside P10-P80; needs its own pass since the cuts are
    # only known once the percentiles above come back.
    core_mean = None
    try:
        core = _core_band(mean_image, stat("p10"), stat("p80"))
        if core is not None:
            core_mean = core.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=aoi, scale=REDUCE_SCALE,
                maxPixels=1e9, bestEffort=True,
            ).getInfo().get(CH4_BAND)
    except Exception:
        core_mean = None

    # Cut is this area's own P80 — hot within this area, not vs. a surrounding
    # box. Non-fatal; error is kept so it's not confused with "no hotspots".
    hotspot_error = None
    try:
        hotspots, hotspot_count = hotspot_regions(
            mean_image, aoi, bbox, stat("p80"), REDUCE_SCALE,
            MAX_HOTSPOT_REGIONS, _describe_patch_above_cut(stat("p80")))
    except Exception as exc:
        hotspots, hotspot_count = None, None
        hotspot_error = f"Hotspot segmentation failed: {exc}"

    histogram = histogram_rows(stats.get(f"{CH4_BAND}_histogram"))
    box = box_stats(histogram, {
        "min": stat("min"), "p10": stat("p10"), "p25": stat("p25"),
        "p50": stat("p50"), "p75": stat("p75"), "p80": stat("p80"),
        "max": stat("max"),
    })

    vis_min, vis_max = _vis_range(stat("p2"), stat("p98"))
    try:
        tiles = _tile_url(mean_image.clip(aoi),
                          {"min": vis_min, "max": vis_max,
                           "palette": CH4_PALETTE})
    except Exception:
        tiles = None

    # `daily_stats` also returns daily means, but the compare page plots no
    # series, so only the availability half is kept. Non-fatal if it fails.
    try:
        _, availability = daily_stats(collection, aoi, CH4_BAND,
                                      REDUCE_SCALE, "ch4")
    except Exception:
        availability = None

    return {
        **state,
        "mean_ch4_ppb": mean_ch4,
        "pass_count": pass_count,
        "error": None,
        "bbox": bbox,
        "min_ch4_ppb": stat("min"),
        "max_ch4_ppb": stat("max"),
        "median_ch4_ppb": stat("p50"),
        "p10_ch4_ppb": stat("p10"),
        "p80_ch4_ppb": stat("p80"),
        "core_mean_ch4_ppb": core_mean,
        "hotspot_threshold_ppb": stat("p80"),
        "hotspots": hotspots,
        "hotspot_region_count": hotspot_count,
        "hotspot_error": hotspot_error,
        "histogram": histogram,
        "box_stats": box,
        "tile_url": tiles,
        "vis_min": vis_min,
        "vis_max": vis_max,
        "availability": availability,
    }


area_graph = StateGraph(AreaState)
area_graph.add_node("fetch_area", fetch_area)
area_graph.set_entry_point("fetch_area")
area_graph.add_edge("fetch_area", END)
area_workflow = area_graph.compile()


def run_area_pipeline(region_name=None, city_name=None, N=None, S=None,
                      W=None, E=None, date_start="", date_end=""):
    """Describe one area on its own terms. No background is computed anywhere."""
    initial_state: AreaState = {
        "region_name": region_name, "city_name": city_name,
        "N": N, "S": S, "W": W, "E": E,
        "date_start": date_start, "date_end": date_end,
        "mean_ch4_ppb": None, "pass_count": None, "error": None, "bbox": None,
        "min_ch4_ppb": None, "max_ch4_ppb": None, "median_ch4_ppb": None,
        "p10_ch4_ppb": None, "p80_ch4_ppb": None, "core_mean_ch4_ppb": None,
        "hotspot_threshold_ppb": None, "hotspot_region_count": None,
        "hotspot_error": None, "hotspots": None,
        "histogram": None, "box_stats": None,
        "tile_url": None, "vis_min": None, "vis_max": None,
        "availability": None,
    }
    return area_workflow.invoke(initial_state)
