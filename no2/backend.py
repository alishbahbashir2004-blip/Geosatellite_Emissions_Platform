# no2/backend.py
# LangGraph workflow: NO2 columns from Earth Engine vs a padded background box,
# mirroring the CO pipeline; gas-specific numbers come from no2/config.py.

import ee
from datetime import datetime, timedelta
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from shared.earthengine import init as ee_init, tile_url as _tile_url
from shared.geo import resolve_bbox, context_bbox
from shared.pipeline import daily_stats, hotspot_regions
from shared.stats import histogram_rows, box_stats
from shared.levels import classify
from no2.config import (
    NO2_ASSET, NO2_BAND, UNIT_SCALE, REDUCE_SCALE, BACKGROUND_SCALE,
    HISTOGRAM_BUCKETS, EMISSION_LEVELS, NO2_PALETTE, NO2_VIS_FALLBACK,
    MIN_VIS_SPREAD, MAX_HOTSPOT_REGIONS,
)

ee_init()

# Re-exported so the NO2 page can offer a location without importing shared
# directly, mirroring how the other gas pages do it.
__all__ = ["run_pipeline", "run_area_pipeline", "resolve_bbox",
          "classify_enhancement", "NO2State", "AreaState"]


def classify_enhancement(enhancement_pct: Optional[float]):
    """Map an NO2 enhancement (% of background) to a level; percent, not
    absolute, since the regional background shifts with season/urbanization."""
    return classify(enhancement_pct, EMISSION_LEVELS)


def _pct_above(value, background):
    """`value` as a percentage above `background`, or None; guards a non-positive
    background (a reduction failure, not clean air) producing a bogus value."""
    if value is None or background is None or background <= 0:
        return None
    return 100.0 * (value - background) / background


def _prepared_collection(date_start, date_end):
    """NO2 images for the period, scaled to umol/m2 once so nothing downstream
    converts units."""
    def prepare(image):
        # multiply() drops the image's properties; daily_stats needs
        # system:time_start, so carry it over by hand.
        return (image.select(NO2_BAND).multiply(UNIT_SCALE).rename(NO2_BAND)
                .set("system:time_start", image.get("system:time_start")))

    return (ee.ImageCollection(NO2_ASSET)
            .filterDate(date_start, date_end)
            .map(prepare))


def _spread_reducer():
    """Combined reducer (mean, min/max, percentiles, histogram) — one round
    trip for every AOI-wide number."""
    return (ee.Reducer.mean()
            .combine(reducer2=ee.Reducer.minMax(), sharedInputs=True)
            .combine(reducer2=ee.Reducer.percentile([2, 10, 25, 50, 75, 80, 98]),
                     sharedInputs=True)
            .combine(reducer2=ee.Reducer.histogram(maxBuckets=HISTOGRAM_BUCKETS),
                     sharedInputs=True))


def _core_band(image, low, high):
    """The band with everything outside the given P10-P80 masked away."""
    if low is None or high is None:
        return None
    band = image.select(NO2_BAND)
    return band.updateMask(band.gte(low).And(band.lte(high)))


def _vis_range(p2, p98):
    """Colour stretch: the AOI's own percentiles, or the fallback if degenerate."""
    if p2 is not None and p98 is not None and p98 - p2 > MIN_VIS_SPREAD:
        return float(p2), float(p98)
    return NO2_VIS_FALLBACK


def _describe_patch(background):
    """NO2 fields for each hotspot patch (shared.pipeline.hotspot_regions):
    level is assigned on percent enhancement; absolute is what the tooltip shows."""
    def describe(patch_mean, patch_max):
        absolute = None if background is None else patch_mean - background
        percent = _pct_above(patch_mean, background)
        level, level_color = classify_enhancement(percent)
        return {
            "mean_no2": patch_mean,
            "max_no2": patch_max,
            "enhancement_no2": absolute,
            "enhancement_pct": percent,
            "level": level,
            "level_color": level_color,
        }
    return describe


# ---- Workflow state ---------------------------------------------------------
class NO2State(TypedDict):
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
    mean_no2: Optional[float]          # AOI mean, umol/m2
    pass_count: Optional[int]
    error: Optional[str]
    bbox: Optional[dict]               # {N, S, W, E} of the area queried
    background_no2: Optional[float]    # padded box around it, same period
    enhancement_no2: Optional[float]   # mean - background, umol/m2
    enhancement_pct: Optional[float]   # the same as a % of background — the
                                       #   quantity the levels classify
    level: Optional[str]
    level_color: Optional[str]
    # --- the same comparison with both tails trimmed off each side ---
    core_mean_no2: Optional[float]     # mean of AOI pixels in P10-P80
    bg_p10_no2: Optional[float]        # background's own percentiles,
    bg_p80_no2: Optional[float]        #   measured over the wider box
    bg_core_mean_no2: Optional[float]  # mean of background P10-P80
    bg_histogram: Optional[list]
    bg_box_stats: Optional[dict]
    core_enhancement_no2: Optional[float]
    core_enhancement_pct: Optional[float]
    core_level: Optional[str]
    # --- hot end of the box, where a localised plume shows up ---
    hotspot_enhancement_no2: Optional[float]   # P80 - background
    hotspot_enhancement_pct: Optional[float]
    hotspot_level: Optional[str]
    peak_enhancement_no2: Optional[float]      # max - background
    peak_enhancement_pct: Optional[float]
    hotspot_threshold_no2: Optional[float]     # P80, the cut the boxes use
    hotspot_region_count: Optional[int]
    hotspot_error: Optional[str]
    hotspots: Optional[list]
    # --- pixel distribution of the composite ---
    histogram: Optional[list]
    box_stats: Optional[dict]
    tile_url: Optional[str]            # NO2 raster clipped to the AOI
    context_tile_url: Optional[str]    # NO2 raster over the surrounding area
    vis_min: Optional[float]
    vis_max: Optional[float]
    # --- spread of the period-mean image across the pixels of the box ---
    min_no2: Optional[float]
    max_no2: Optional[float]
    median_no2: Optional[float]
    p10_no2: Optional[float]
    p80_no2: Optional[float]
    # --- time series and coverage ---
    series: Optional[list]             # [{date, no2}]
    availability: Optional[list]       # [{date, sample_count, valid_count,
                                       #   no_data_count}]


# ---- Node: fetch NO2 columns from Earth Engine ------------------------------
def fetch_no2(state: NO2State) -> NO2State:
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

    base = _prepared_collection(start_dt.strftime("%Y-%m-%d"),
                                end_dt.strftime("%Y-%m-%d"))
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
        return stats.get(f"{NO2_BAND}_{name}")

    mean_no2, p2, p98 = stat("mean"), stat("p2"), stat("p98")

    if mean_no2 is None:
        return {**state, "bbox": bbox, "pass_count": pass_count,
                "error": "No NO2 pixels survived masking over this area and "
                         "period. Try a longer date range."}

    # Local background: same period, wider box so the context layer is fully
    # covered. Non-fatal if it fails — costs the classification, not the page.
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
            geometry=context_aoi, scale=BACKGROUND_SCALE,
            maxPixels=1e9, bestEffort=True,
        ).getInfo()
        background = bg_stats.get(f"{NO2_BAND}_mean")
        bg_p10 = bg_stats.get(f"{NO2_BAND}_p10")
        bg_p80 = bg_stats.get(f"{NO2_BAND}_p80")
        # Whole background distribution, not just P10-P80, so the two
        # histograms on the page band the same range and read against each other.
        bg_histogram = histogram_rows(bg_stats.get(f"{NO2_BAND}_histogram"))
        bg_box = box_stats(bg_histogram, {
            "min": bg_stats.get(f"{NO2_BAND}_min"), "p10": bg_p10,
            "p80": bg_p80, "max": bg_stats.get(f"{NO2_BAND}_max"),
        })
    except Exception:
        background = bg_p10 = bg_p80 = None
        bg_histogram = bg_box = None

    # Mean of P10-P80 pixels, AOI and background — trims both tails to compare
    # two bulk levels, not two averages. Both regions go out in one round trip.
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
            core_mean = (got.get("aoi") or {}).get(NO2_BAND)
            bg_core_mean = (got.get("bg") or {}).get(NO2_BAND)
    except Exception:
        core_mean = bg_core_mean = None

    # The headline comparison with both tails taken off each side.
    core_absolute = core_pct = None
    if core_mean is not None and bg_core_mean is not None:
        core_absolute = core_mean - bg_core_mean
        core_pct = _pct_above(core_mean, bg_core_mean)
    core_level, _ = classify_enhancement(core_pct)

    enhancement = (None if (mean_no2 is None or background is None)
                   else mean_no2 - background)
    enhancement_pct = _pct_above(mean_no2, background)
    level, level_color = classify_enhancement(enhancement_pct)

    # Same comparison at the hot end of the box: a small plume barely moves
    # the area mean, so P80 and the peak value are measured against background too.
    def above_background(value):
        if value is None or background is None:
            return None, None
        return value - background, _pct_above(value, background)

    hotspot_absolute, hotspot_pct = above_background(stat("p80"))
    peak_absolute, peak_pct = above_background(stat("max"))
    hotspot_level, _ = classify_enhancement(hotspot_pct)

    # Where in the box that hot fifth sits. Non-fatal, but the error is kept:
    # a silently missing overlay would look identical to "no hotspots found".
    hotspot_error = None
    try:
        hotspots, hotspot_count = hotspot_regions(
            mean_image, aoi, bbox, stat("p80"), REDUCE_SCALE,
            MAX_HOTSPOT_REGIONS, _describe_patch(background))
    except Exception as exc:
        hotspots, hotspot_count = None, None
        hotspot_error = f"Hotspot segmentation failed: {exc}"

    histogram = histogram_rows(stats.get(f"{NO2_BAND}_histogram"))
    box = box_stats(histogram, {
        "min": stat("min"), "p10": stat("p10"), "p25": stat("p25"),
        "p50": stat("p50"), "p75": stat("p75"), "p80": stat("p80"),
        "max": stat("max"),
    })

    vis_min, vis_max = _vis_range(p2, p98)
    vis = {"min": vis_min, "max": vis_max, "palette": NO2_PALETTE}
    try:
        tiles = _tile_url(mean_image.clip(aoi), vis)
        context_tiles = _tile_url(context_mean_image.clip(context_aoi), vis)
    except Exception:
        tiles = context_tiles = None

    # Chart data. Also non-fatal: the numbers and map still stand without it.
    try:
        series, availability = daily_stats(collection, aoi, NO2_BAND,
                                           REDUCE_SCALE, "no2")
    except Exception:
        series, availability = None, None

    return {
        **state,
        "mean_no2": mean_no2,
        "pass_count": pass_count,
        "error": None,
        "bbox": bbox,
        "background_no2": background,
        "enhancement_no2": enhancement,
        "enhancement_pct": enhancement_pct,
        "level": level,
        "level_color": level_color,
        "tile_url": tiles,
        "context_tile_url": context_tiles,
        "vis_min": vis_min,
        "vis_max": vis_max,
        "series": series,
        "availability": availability,
        "min_no2": stat("min"),
        "max_no2": stat("max"),
        "median_no2": stat("p50"),
        "p10_no2": stat("p10"),
        "p80_no2": stat("p80"),
        "core_mean_no2": core_mean,
        "bg_p10_no2": bg_p10,
        "bg_p80_no2": bg_p80,
        "bg_core_mean_no2": bg_core_mean,
        "bg_histogram": bg_histogram,
        "bg_box_stats": bg_box,
        "core_enhancement_no2": core_absolute,
        "core_enhancement_pct": core_pct,
        "core_level": core_level,
        "hotspot_enhancement_no2": hotspot_absolute,
        "hotspot_enhancement_pct": hotspot_pct,
        "hotspot_level": hotspot_level,
        "peak_enhancement_no2": peak_absolute,
        "peak_enhancement_pct": peak_pct,
        "hotspot_threshold_no2": stat("p80"),
        "hotspots": hotspots,
        "hotspot_region_count": hotspot_count,
        "hotspot_error": hotspot_error,
        "histogram": histogram,
        "box_stats": box,
    }


# ---- Build the graph (single node for now; more steps come later) -----------
graph = StateGraph(NO2State)
graph.add_node("fetch_no2", fetch_no2)
graph.set_entry_point("fetch_no2")
graph.add_edge("fetch_no2", END)
workflow = graph.compile()


# ---- Convenience wrapper for the frontend -----------------------------------
def run_pipeline(region_name=None, city_name=None, N=None, S=None, W=None,
                 E=None, date_start="", date_end=""):
    """Run the NO2 pipeline and return the finished state dict."""
    initial_state: NO2State = {
        "region_name": region_name, "city_name": city_name,
        "N": N, "S": S, "W": W, "E": E,
        "date_start": date_start, "date_end": date_end,
        "mean_no2": None, "pass_count": None, "error": None, "bbox": None,
        "background_no2": None, "enhancement_no2": None,
        "enhancement_pct": None, "level": None, "level_color": None,
        "core_mean_no2": None, "bg_p10_no2": None, "bg_p80_no2": None,
        "bg_core_mean_no2": None, "bg_histogram": None, "bg_box_stats": None,
        "core_enhancement_no2": None, "core_enhancement_pct": None,
        "core_level": None,
        "hotspot_enhancement_no2": None, "hotspot_enhancement_pct": None,
        "hotspot_level": None, "peak_enhancement_no2": None,
        "peak_enhancement_pct": None, "hotspot_threshold_no2": None,
        "hotspot_region_count": None, "hotspot_error": None, "hotspots": None,
        "histogram": None, "box_stats": None,
        "tile_url": None, "context_tile_url": None,
        "vis_min": None, "vis_max": None,
        "min_no2": None, "max_no2": None, "median_no2": None,
        "p10_no2": None, "p80_no2": None,
        "series": None, "availability": None,
    }
    return workflow.invoke(initial_state)


# ---- The background-free pipeline -------------------------------------------
# For the compare view: one AOI on its own terms — no padded box, background,
# enhancement, or level. See ch4/backend.py's note for why, not a cheaper version.


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
    mean_no2: Optional[float]
    pass_count: Optional[int]
    error: Optional[str]
    bbox: Optional[dict]               # {N, S, W, E} of the area queried
    # --- spread of the period-mean image across the pixels of the box ---
    min_no2: Optional[float]
    max_no2: Optional[float]
    median_no2: Optional[float]
    p10_no2: Optional[float]
    p80_no2: Optional[float]
    core_mean_no2: Optional[float]     # mean of the pixels inside P10-P80
    # --- hot end of the box, measured against the box's own P80 ---
    hotspot_threshold_no2: Optional[float]   # the AOI's own P80: the only cut
    hotspot_region_count: Optional[int]      # patches found, before the cap
    hotspot_error: Optional[str]
    hotspots: Optional[list]                 # [{N,S,W,E, mean_no2, max_no2,
                                             #   pixel_count, fill_pct,
                                             #   above_cut_no2}] hottest first
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
    """NO2 fields for a hotspot patch with no background: just how far above
    the AOI's own P80 it sits. No level/percent — both need a background."""
    def describe(patch_mean, patch_max):
        return {
            "mean_no2": patch_mean,
            "max_no2": patch_max,
            "above_cut_no2": None if cut is None else patch_mean - cut,
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

    collection = _prepared_collection(
        start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"),
    ).filterBounds(aoi)

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
        return stats.get(f"{NO2_BAND}_{name}")

    mean_no2 = stat("mean")
    if mean_no2 is None:
        return {**state, "bbox": bbox, "pass_count": pass_count,
                "error": "No NO2 pixels survived masking over this area and "
                         "period. Try a longer date range."}

    # Mean of the pixels inside P10-P80. Needs its own pass, because the cuts
    # are only known once the percentiles above come back.
    core_mean = None
    try:
        core = _core_band(mean_image, stat("p10"), stat("p80"))
        if core is not None:
            core_mean = core.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=aoi, scale=REDUCE_SCALE,
                maxPixels=1e9, bestEffort=True,
            ).getInfo().get(NO2_BAND)
    except Exception:
        core_mean = None

    # Hotspots here are relative to this area's own P80 only — no surrounding
    # box. Non-fatal; the error is kept since a missing overlay looks like "none found".
    hotspot_error = None
    try:
        hotspots, hotspot_count = hotspot_regions(
            mean_image, aoi, bbox, stat("p80"), REDUCE_SCALE,
            MAX_HOTSPOT_REGIONS, _describe_patch_above_cut(stat("p80")))
    except Exception as exc:
        hotspots, hotspot_count = None, None
        hotspot_error = f"Hotspot segmentation failed: {exc}"

    histogram = histogram_rows(stats.get(f"{NO2_BAND}_histogram"))
    box = box_stats(histogram, {
        "min": stat("min"), "p10": stat("p10"), "p25": stat("p25"),
        "p50": stat("p50"), "p75": stat("p75"), "p80": stat("p80"),
        "max": stat("max"),
    })

    vis_min, vis_max = _vis_range(stat("p2"), stat("p98"))
    try:
        tiles = _tile_url(mean_image.clip(aoi),
                          {"min": vis_min, "max": vis_max,
                           "palette": NO2_PALETTE})
    except Exception:
        tiles = None

    # How much of the box each day's passes delivered. Non-fatal; daily_stats
    # also returns daily means, but the compare page plots no series, so only this is kept.
    try:
        _, availability = daily_stats(collection, aoi, NO2_BAND,
                                      REDUCE_SCALE, "no2")
    except Exception:
        availability = None

    return {
        **state,
        "mean_no2": mean_no2,
        "pass_count": pass_count,
        "error": None,
        "bbox": bbox,
        "min_no2": stat("min"),
        "max_no2": stat("max"),
        "median_no2": stat("p50"),
        "p10_no2": stat("p10"),
        "p80_no2": stat("p80"),
        "core_mean_no2": core_mean,
        "hotspot_threshold_no2": stat("p80"),
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
        "mean_no2": None, "pass_count": None, "error": None, "bbox": None,
        "min_no2": None, "max_no2": None, "median_no2": None,
        "p10_no2": None, "p80_no2": None, "core_mean_no2": None,
        "hotspot_threshold_no2": None, "hotspot_region_count": None,
        "hotspot_error": None, "hotspots": None,
        "histogram": None, "box_stats": None,
        "tile_url": None, "vis_min": None, "vis_max": None,
        "availability": None,
    }
    return area_workflow.invoke(initial_state)
