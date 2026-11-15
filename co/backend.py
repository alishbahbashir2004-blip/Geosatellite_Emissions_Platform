# co/backend.py
# LangGraph workflow: pulls Sentinel-5P CO (mmol/m2), compares to a padded
# background box. CH4's sibling, plus cloud filtering and reported "regional loading".

import ee
from datetime import datetime, timedelta
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from shared.earthengine import init as ee_init, tile_url as _tile_url
from shared.geo import resolve_bbox, context_bbox
from shared.pipeline import daily_stats, hotspot_regions
from shared.stats import histogram_rows, box_stats
from shared.levels import classify
from co.config import (
    CO_ASSET, CO_BAND, CLOUD_BAND, UNIT_SCALE,
    DEFAULT_CLOUD_CEILING_M, CLEAR_SKY_DEFAULT,
    REDUCE_SCALE, BACKGROUND_SCALE, HISTOGRAM_BUCKETS,
    EMISSION_LEVELS, REGIONAL_LOADING_LEVELS, LOADING_NOTES,
    CO_PALETTE, CO_VIS_FALLBACK, MIN_VIS_SPREAD, MAX_HOTSPOT_REGIONS,
)

ee_init()

# Re-exported so the CO page can offer a location without importing shared
# directly, mirroring the methane page's own backend.
__all__ = ["run_pipeline", "run_area_pipeline", "resolve_bbox",
           "classify_enhancement", "classify_loading", "COState",
           "COAreaState"]


def classify_enhancement(enhancement_pct: Optional[float]):
    """Map a CO enhancement (percent of local background) to a level; percent,
    not mmol/m2 — see EMISSION_LEVELS."""
    return classify(enhancement_pct, EMISSION_LEVELS)


def classify_loading(background_co: Optional[float]):
    """Map the absolute background column to a regional-loading level — "is
    this scene clean?", separate from "is this area above its surroundings?"."""
    label, color = classify(background_co, REGIONAL_LOADING_LEVELS)
    return label, color, LOADING_NOTES.get(label)


def _pct_above(value, background):
    """`value` as % above `background`, or None. Guarded on non-positive
    background: zero/negative means a reduction failure, not clean air."""
    if value is None or background is None or background <= 0:
        return None
    return 100.0 * (value - background) / background


def _prepared_collection(date_start, date_end, cloud_ceiling):
    """CO images for the period, cloud-filtered and scaled to mmol/m2, done
    once here so everything downstream is already in the reported unit."""
    def prepare(image):
        band = image.select(CO_BAND)
        if cloud_ceiling is not None:
            # Low scattering height means the retrieval reached near the
            # surface, where a flare or stack would be.
            band = band.updateMask(image.select(CLOUD_BAND).lte(cloud_ceiling))
        # multiply() drops image properties; daily_stats needs the timestamp
        # to group passes into days, so it's carried over by hand.
        return (band.multiply(UNIT_SCALE).rename(CO_BAND)
                .set("system:time_start", image.get("system:time_start")))

    return (ee.ImageCollection(CO_ASSET)
            .filterDate(date_start, date_end)
            .map(prepare))


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
    """The band with everything outside the given P10-P80 masked away."""
    if low is None or high is None:
        return None
    band = image.select(CO_BAND)
    return band.updateMask(band.gte(low).And(band.lte(high)))


def _vis_range(p2, p98):
    """Colour stretch: the AOI's own percentiles, or the fallback if degenerate
    (a flat scene would otherwise stretch noise into a fake plume)."""
    if p2 is not None and p98 is not None and p98 - p2 > MIN_VIS_SPREAD:
        return float(p2), float(p98)
    return CO_VIS_FALLBACK


def _describe_patch(background):
    """CO fields per hotspot patch: carries both absolute and percent
    enhancement (level is assigned on percent; absolute is what the tooltip shows)."""
    def describe(patch_mean, patch_max):
        absolute = None if background is None else patch_mean - background
        percent = _pct_above(patch_mean, background)
        level, level_color = classify_enhancement(percent)
        return {
            "mean_co": patch_mean,
            "max_co": patch_max,
            "enhancement_co": absolute,
            "enhancement_pct": percent,
            "level": level,
            "level_color": level_color,
        }
    return describe


# ---- Workflow state ---------------------------------------------------------
class COState(TypedDict):
    # --- inputs ---
    region_name: Optional[str]
    city_name: Optional[str]
    N: Optional[float]
    S: Optional[float]
    W: Optional[float]
    E: Optional[float]
    date_start: str
    date_end: str
    clear_sky: Optional[bool]          # drop cloudy scenes (see config.py)
    cloud_ceiling_m: Optional[float]   # the ceiling actually applied, or None
    # --- headline ---
    mean_co: Optional[float]           # AOI mean, mmol/m2
    pass_count: Optional[int]
    error: Optional[str]
    bbox: Optional[dict]               # {N, S, W, E} of the area queried
    background_co: Optional[float]     # padded box around it, same period
    enhancement_co: Optional[float]    # mean - background, mmol/m2
    enhancement_pct: Optional[float]   # the same as a % of background — the
                                       #   quantity the levels classify
    level: Optional[str]
    level_color: Optional[str]
    # --- is the scene itself clean? CO's wildfire-smoke confounder ---
    loading_level: Optional[str]
    loading_color: Optional[str]
    loading_note: Optional[str]
    # --- the same comparison with both tails trimmed off each side ---
    core_mean_co: Optional[float]      # mean of AOI pixels in P10-P80
    bg_p10_co: Optional[float]         # background's own percentiles,
    bg_p80_co: Optional[float]         #   measured over the wider box
    bg_core_mean_co: Optional[float]   # mean of background P10-P80
    bg_histogram: Optional[list]       # [{value,start,end,count}]
    bg_box_stats: Optional[dict]       # its min, max and P10/P80 cuts
    core_enhancement_co: Optional[float]
    core_enhancement_pct: Optional[float]
    core_level: Optional[str]
    # --- hot end of the box, where a localised plume shows up ---
    hotspot_enhancement_co: Optional[float]   # P80 - background
    hotspot_enhancement_pct: Optional[float]
    hotspot_level: Optional[str]
    peak_enhancement_co: Optional[float]      # max - background
    peak_enhancement_pct: Optional[float]
    hotspot_threshold_co: Optional[float]     # P80, the cut the boxes use
    hotspot_region_count: Optional[int]
    hotspot_error: Optional[str]
    hotspots: Optional[list]
    # --- pixel distribution of the composite ---
    histogram: Optional[list]
    box_stats: Optional[dict]
    tile_url: Optional[str]            # CO raster clipped to the AOI
    context_tile_url: Optional[str]    # CO raster over the surrounding area
    vis_min: Optional[float]
    vis_max: Optional[float]
    # --- spread of the period-mean image across the pixels of the box ---
    min_co: Optional[float]
    max_co: Optional[float]
    median_co: Optional[float]
    p10_co: Optional[float]
    p80_co: Optional[float]
    # --- time series and coverage ---
    series: Optional[list]             # [{date, co}]
    availability: Optional[list]       # [{date, sample_count, valid_count,
                                       #   no_data_count}]


# ---- Node: fetch CO columns from Earth Engine -------------------------------
def fetch_co(state: COState) -> COState:
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

    clear_sky = state.get("clear_sky")
    if clear_sky is None:
        clear_sky = CLEAR_SKY_DEFAULT
    ceiling = state.get("cloud_ceiling_m") or DEFAULT_CLOUD_CEILING_M
    cloud_ceiling = float(ceiling) if clear_sky else None

    base = _prepared_collection(date_start_str, date_end_str, cloud_ceiling)
    collection = base.filterBounds(aoi)

    applied = {"clear_sky": bool(clear_sky), "cloud_ceiling_m": cloud_ceiling}

    try:
        pass_count = collection.size().getInfo()
    except Exception as exc:
        return {**state, **applied,
                "error": f"Earth Engine error getting collection size: {exc}"}

    if pass_count == 0:
        return {**state, **applied, "bbox": bbox,
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
        return {**state, **applied, "bbox": bbox,
                "error": f"Earth Engine error reducing region: {exc}"}

    def stat(name):
        """Pull one reducer output; they all come back band-name prefixed."""
        return stats.get(f"{CO_BAND}_{name}")

    mean_co, p2, p98 = stat("mean"), stat("p2"), stat("p98")

    if mean_co is None:
        # Every pixel was masked away; with the clear-sky filter on, say
        # which knob to turn rather than reporting an empty result.
        reason = ("No CO pixels survived masking over this area and period."
                  + (f" The clear-sky filter (cloud height ≤ {cloud_ceiling:.0f} m)"
                     " is on — try turning it off or raising the ceiling."
                     if cloud_ceiling is not None else
                     " Try a longer date range."))
        return {**state, **applied, "bbox": bbox, "pass_count": pass_count,
                "error": reason}

    # Local background: same period, surrounding area, using passes over the
    # wider box. Non-fatal if it fails — costs classification, not the page.
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
        background = bg_stats.get(f"{CO_BAND}_mean")
        bg_p10 = bg_stats.get(f"{CO_BAND}_p10")
        bg_p80 = bg_stats.get(f"{CO_BAND}_p80")
        # Whole background distribution, not just the P10-P80 slice, so this
        # chart bands the same range as the AOI chart and the two compare.
        bg_histogram = histogram_rows(bg_stats.get(f"{CO_BAND}_histogram"))
        bg_box = box_stats(bg_histogram, {
            "min": bg_stats.get(f"{CO_BAND}_min"), "p10": bg_p10,
            "p80": bg_p80, "max": bg_stats.get(f"{CO_BAND}_max"),
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
            core_mean = (got.get("aoi") or {}).get(CO_BAND)
            bg_core_mean = (got.get("bg") or {}).get(CO_BAND)
    except Exception:
        core_mean = bg_core_mean = None

    # Is the scene itself clean? Read off the absolute background column,
    # independent of whether the AOI stands above it.
    loading_level, loading_color, loading_note = classify_loading(background)

    # The headline comparison with both tails taken off each side.
    core_absolute = core_pct = None
    if core_mean is not None and bg_core_mean is not None:
        core_absolute = core_mean - bg_core_mean
        core_pct = _pct_above(core_mean, bg_core_mean)
    core_level, _ = classify_enhancement(core_pct)

    enhancement = None if (mean_co is None or background is None) else mean_co - background
    enhancement_pct = _pct_above(mean_co, background)
    level, level_color = classify_enhancement(enhancement_pct)

    # Same comparison at the hot end: P80 and peak vs. background, since a
    # small plume barely moves the area mean.
    def above_background(value):
        if value is None or background is None:
            return None, None
        return value - background, _pct_above(value, background)

    hotspot_absolute, hotspot_pct = above_background(stat("p80"))
    peak_absolute, peak_pct = above_background(stat("max"))
    hotspot_level, _ = classify_enhancement(hotspot_pct)

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
    histogram = histogram_rows(stats.get(f"{CO_BAND}_histogram"))
    box = box_stats(histogram, {
        "min": stat("min"), "p10": stat("p10"), "p25": stat("p25"),
        "p50": stat("p50"), "p75": stat("p75"), "p80": stat("p80"),
        "max": stat("max"),
    })

    # Colour stretch: prefer the AOI's own percentiles, fall back when
    # missing or too flat to stretch without faking a plume.
    vis_min, vis_max = _vis_range(p2, p98)

    vis = {"min": vis_min, "max": vis_max, "palette": CO_PALETTE}
    try:
        tiles = _tile_url(mean_image.clip(aoi), vis)
        context_tiles = _tile_url(context_mean_image.clip(context_aoi), vis)
    except Exception:
        tiles = context_tiles = None

    # Chart data. Also non-fatal: the numbers and map still stand without it.
    try:
        series, availability = daily_stats(collection, aoi, CO_BAND,
                                          REDUCE_SCALE, "co")
    except Exception:
        series, availability = None, None

    return {
        **state, **applied,
        "mean_co": mean_co,
        "pass_count": pass_count,
        "error": None,
        "bbox": bbox,
        "background_co": background,
        "enhancement_co": enhancement,
        "enhancement_pct": enhancement_pct,
        "level": level,
        "level_color": level_color,
        "loading_level": loading_level,
        "loading_color": loading_color,
        "loading_note": loading_note,
        "tile_url": tiles,
        "context_tile_url": context_tiles,
        "vis_min": vis_min,
        "vis_max": vis_max,
        "series": series,
        "availability": availability,
        "min_co": stat("min"),
        "max_co": stat("max"),
        "median_co": stat("p50"),
        "p10_co": stat("p10"),
        "p80_co": stat("p80"),
        "core_mean_co": core_mean,
        "bg_p10_co": bg_p10,
        "bg_p80_co": bg_p80,
        "bg_core_mean_co": bg_core_mean,
        "bg_histogram": bg_histogram,
        "bg_box_stats": bg_box,
        "core_enhancement_co": core_absolute,
        "core_enhancement_pct": core_pct,
        "core_level": core_level,
        "hotspot_enhancement_co": hotspot_absolute,
        "hotspot_enhancement_pct": hotspot_pct,
        "hotspot_level": hotspot_level,
        "peak_enhancement_co": peak_absolute,
        "peak_enhancement_pct": peak_pct,
        "hotspot_threshold_co": stat("p80"),
        "hotspots": hotspots,
        "hotspot_region_count": hotspot_count,
        "hotspot_error": hotspot_error,
        "histogram": histogram,
        "box_stats": box,
    }


# ---- Build the graph (single node for now; more steps come later) -----------
graph = StateGraph(COState)
graph.add_node("fetch_co", fetch_co)
graph.set_entry_point("fetch_co")
graph.add_edge("fetch_co", END)
workflow = graph.compile()


# ---- Convenience wrapper for the frontend ----------------------------------
def run_pipeline(region_name=None, city_name=None, N=None, S=None, W=None,
                 E=None, date_start="", date_end="",
                 clear_sky=CLEAR_SKY_DEFAULT,
                 cloud_ceiling_m=DEFAULT_CLOUD_CEILING_M):
    """Run the CO pipeline and return the finished state dict. `clear_sky`
    drops scenes above `cloud_ceiling_m` scattering height, keeping near-surface hits."""
    initial_state: COState = {
        "region_name": region_name, "city_name": city_name,
        "N": N, "S": S, "W": W, "E": E,
        "date_start": date_start, "date_end": date_end,
        "clear_sky": clear_sky, "cloud_ceiling_m": cloud_ceiling_m,
        "mean_co": None, "pass_count": None, "error": None, "bbox": None,
        "background_co": None, "enhancement_co": None,
        "enhancement_pct": None, "level": None, "level_color": None,
        "loading_level": None, "loading_color": None, "loading_note": None,
        "core_mean_co": None, "bg_p10_co": None, "bg_p80_co": None,
        "bg_core_mean_co": None, "bg_histogram": None, "bg_box_stats": None,
        "core_enhancement_co": None, "core_enhancement_pct": None,
        "core_level": None,
        "hotspot_enhancement_co": None, "hotspot_enhancement_pct": None,
        "hotspot_level": None, "peak_enhancement_co": None,
        "peak_enhancement_pct": None, "hotspot_threshold_co": None,
        "hotspot_region_count": None, "hotspot_error": None, "hotspots": None,
        "histogram": None, "box_stats": None,
        "tile_url": None, "context_tile_url": None,
        "vis_min": None, "vis_max": None,
        "min_co": None, "max_co": None, "median_co": None,
        "p10_co": None, "p80_co": None,
        "series": None, "availability": None,
    }
    return workflow.invoke(initial_state)


# ---- The background-free pipeline --------------------------------------------
# Compare view: one AOI alone — no background, enhancement/level, or loading
# verdict. Clear-sky stays; both compared areas must use the same filter.


class COAreaState(TypedDict):
    # --- inputs ---
    region_name: Optional[str]
    city_name: Optional[str]
    N: Optional[float]
    S: Optional[float]
    W: Optional[float]
    E: Optional[float]
    date_start: str
    date_end: str
    clear_sky: Optional[bool]          # drop cloudy scenes (see config.py)
    cloud_ceiling_m: Optional[float]   # the ceiling actually applied, or None
    # --- headline ---
    mean_co: Optional[float]           # AOI mean, mmol/m2
    pass_count: Optional[int]
    error: Optional[str]
    bbox: Optional[dict]               # {N, S, W, E} of the area queried
    # --- spread of the period-mean image across the pixels of the box ---
    min_co: Optional[float]
    max_co: Optional[float]
    median_co: Optional[float]
    p10_co: Optional[float]
    p80_co: Optional[float]
    core_mean_co: Optional[float]      # mean of the pixels inside P10-P80
    # --- hot end of the box, measured against the box's own P80 ---
    hotspot_threshold_co: Optional[float]   # the AOI's own P80: the only cut
    hotspot_region_count: Optional[int]
    hotspot_error: Optional[str]
    hotspots: Optional[list]                # [{N,S,W,E,mean_co,max_co,pixel_count,
                                            #   fill_pct,above_cut_co}], hottest first
    # --- pixel distribution and the raster ---
    histogram: Optional[list]
    box_stats: Optional[dict]
    tile_url: Optional[str]
    vis_min: Optional[float]
    vis_max: Optional[float]
    # --- per-day pixel availability, for the availability chart ---
    availability: Optional[list]       # [{date, sample_count, valid_count,
                                       #   no_data_count}]


def _describe_patch_above_cut(cut):
    """CO fields with no background: how far above the AOI's own P80 it sits.
    No level or percent — those band a percent of a background that doesn't
    exist here."""
    def describe(patch_mean, patch_max):
        return {
            "mean_co": patch_mean,
            "max_co": patch_max,
            "above_cut_co": None if cut is None else patch_mean - cut,
        }
    return describe


def fetch_co_area(state: COAreaState) -> COAreaState:
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

    clear_sky = state.get("clear_sky")
    if clear_sky is None:
        clear_sky = CLEAR_SKY_DEFAULT
    ceiling = state.get("cloud_ceiling_m") or DEFAULT_CLOUD_CEILING_M
    cloud_ceiling = float(ceiling) if clear_sky else None

    collection = _prepared_collection(
        start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"),
        cloud_ceiling,
    ).filterBounds(aoi)

    applied = {"clear_sky": bool(clear_sky), "cloud_ceiling_m": cloud_ceiling}

    try:
        pass_count = collection.size().getInfo()
    except Exception as exc:
        return {**state, **applied,
                "error": f"Earth Engine error getting collection size: {exc}"}

    if pass_count == 0:
        return {**state, **applied, "bbox": bbox,
                "error": "No satellite passes found for this region/date range."}

    mean_image = collection.mean()

    try:
        stats = mean_image.reduceRegion(
            reducer=_spread_reducer(), geometry=aoi, scale=REDUCE_SCALE,
            maxPixels=1e9, bestEffort=True,
        ).getInfo()
    except Exception as exc:
        return {**state, **applied, "bbox": bbox,
                "error": f"Earth Engine error reducing region: {exc}"}

    def stat(name):
        """Pull one reducer output; they all come back band-name prefixed."""
        return stats.get(f"{CO_BAND}_{name}")

    mean_co = stat("mean")
    if mean_co is None:
        # Every pixel was masked away; say which knob to turn.
        reason = ("No CO pixels survived masking over this area and period."
                  + (f" The clear-sky filter (cloud height ≤ {cloud_ceiling:.0f} m)"
                     " is on — try turning it off or raising the ceiling."
                     if cloud_ceiling is not None else
                     " Try a longer date range."))
        return {**state, **applied, "bbox": bbox, "pass_count": pass_count,
                "error": reason}

    # Mean of pixels inside P10-P80; needs its own pass since the cuts are
    # only known once the percentiles above come back.
    core_mean = None
    try:
        core = _core_band(mean_image, stat("p10"), stat("p80"))
        if core is not None:
            core_mean = core.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=aoi, scale=REDUCE_SCALE,
                maxPixels=1e9, bestEffort=True,
            ).getInfo().get(CO_BAND)
    except Exception:
        core_mean = None

    # Cut is this area's own P80 and nothing else. Non-fatal; error is kept
    # so a missing overlay isn't confused with "no hotspots found".
    hotspot_error = None
    try:
        hotspots, hotspot_count = hotspot_regions(
            mean_image, aoi, bbox, stat("p80"), REDUCE_SCALE,
            MAX_HOTSPOT_REGIONS, _describe_patch_above_cut(stat("p80")))
    except Exception as exc:
        hotspots, hotspot_count = None, None
        hotspot_error = f"Hotspot segmentation failed: {exc}"

    histogram = histogram_rows(stats.get(f"{CO_BAND}_histogram"))
    box = box_stats(histogram, {
        "min": stat("min"), "p10": stat("p10"), "p25": stat("p25"),
        "p50": stat("p50"), "p75": stat("p75"), "p80": stat("p80"),
        "max": stat("max"),
    })

    vis_min, vis_max = _vis_range(stat("p2"), stat("p98"))
    try:
        tiles = _tile_url(mean_image.clip(aoi),
                          {"min": vis_min, "max": vis_max,
                           "palette": CO_PALETTE})
    except Exception:
        tiles = None

    # Reflects the product's quality mask plus the clear-sky filter when on.
    # Only availability is kept — compare page plots no series.
    try:
        _, availability = daily_stats(collection, aoi, CO_BAND,
                                      REDUCE_SCALE, "co")
    except Exception:
        availability = None

    return {
        **state, **applied,
        "mean_co": mean_co,
        "pass_count": pass_count,
        "error": None,
        "bbox": bbox,
        "min_co": stat("min"),
        "max_co": stat("max"),
        "median_co": stat("p50"),
        "p10_co": stat("p10"),
        "p80_co": stat("p80"),
        "core_mean_co": core_mean,
        "hotspot_threshold_co": stat("p80"),
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


area_graph = StateGraph(COAreaState)
area_graph.add_node("fetch_co_area", fetch_co_area)
area_graph.set_entry_point("fetch_co_area")
area_graph.add_edge("fetch_co_area", END)
area_workflow = area_graph.compile()


def run_area_pipeline(region_name=None, city_name=None, N=None, S=None,
                      W=None, E=None, date_start="", date_end="",
                      clear_sky=CLEAR_SKY_DEFAULT,
                      cloud_ceiling_m=DEFAULT_CLOUD_CEILING_M):
    """Describe one area alone; no background computed. `clear_sky` behaves as
    in run_pipeline: drops scenes above `cloud_ceiling_m`, keeping near-surface hits."""
    initial_state: COAreaState = {
        "region_name": region_name, "city_name": city_name,
        "N": N, "S": S, "W": W, "E": E,
        "date_start": date_start, "date_end": date_end,
        "clear_sky": clear_sky, "cloud_ceiling_m": cloud_ceiling_m,
        "mean_co": None, "pass_count": None, "error": None, "bbox": None,
        "min_co": None, "max_co": None, "median_co": None,
        "p10_co": None, "p80_co": None, "core_mean_co": None,
        "hotspot_threshold_co": None, "hotspot_region_count": None,
        "hotspot_error": None, "hotspots": None,
        "histogram": None, "box_stats": None,
        "tile_url": None, "vis_min": None, "vis_max": None,
        "availability": None,
    }
    return area_workflow.invoke(initial_state)
