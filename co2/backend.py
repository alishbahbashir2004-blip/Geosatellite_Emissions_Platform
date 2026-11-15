# co2/backend.py
# The five CO2 analyses, each queried separately (different resolution,
# coverage, claim). Unavailable results return reason/detail instead of a metric.

from datetime import date

from shared.geo import resolve_bbox, context_bbox
from co2 import sources
from co2.analysis import (adequacy, coverage_gap, clamp_to_coverage, decompose,
                          anomaly_between, classify_anomaly, infer_from_no2,
                          inventory_totals)
from co2.config import (SOURCES, TREND_SAMPLE_DAYS, MIN_YEARS_FOR_SEASONAL,
                        NO2_COVERAGE_START, ODIAC_CO2_BREAKS,
                        ODIAC_CLASS_COLORS, CARBON_TO_CO2, SAM_COLORMAP,
                        SAM_PAD_PPM, MIN_PLAUSIBLE_PPM)

__all__ = ["resolve_bbox", "context_bbox", "coverage_timeline", "run_trend",
           "run_anomaly", "run_inventory", "run_snapshots", "run_inferred"]


def _unavailable(reason, detail, **extra):
    return {"available": False, "reason": reason, "detail": detail, **extra}


def _too_small(check):
    return _unavailable(
        "Your area is smaller than this product can resolve",
        check["suggestion"], adequacy=check)


def _outside_coverage(source_key, date_start, date_end):
    low, high = SOURCES[source_key]["coverage"]
    return _unavailable(
        f"{SOURCES[source_key]['label']} has no data for these dates",
        f"This product covers {low} to {high}. You asked for "
        f"{date_start} to {date_end}, which does not overlap it at all.",
        source_range=(low, high))


# ---------------------------------------------------------------------------
# Coverage timeline — what exists, and when
# ---------------------------------------------------------------------------

def coverage_timeline(date_start, date_end):
    """One row per product: its window, and whether it covers the request."""
    rows = []
    for key, source in SOURCES.items():
        low, high = source["coverage"]
        overlap = clamp_to_coverage(key, date_start, date_end)
        rows.append({
            "key": key, "label": source["label"], "kind": source["kind"],
            "start": low, "end": high,
            "overlap_start": overlap[0] if overlap else None,
            "overlap_end": overlap[1] if overlap else None,
            "covers_request": overlap is not None,
            "ends_before_today": high < date.today().isoformat(),
        })
    rows.append({
        "key": "no2", "label": "Sentinel-5P NO2 (for inference)",
        "kind": "observation",
        "start": NO2_COVERAGE_START, "end": date.today().isoformat(),
        "overlap_start": max(date_start, NO2_COVERAGE_START),
        "overlap_end": date_end,
        "covers_request": date_end >= NO2_COVERAGE_START,
        "ends_before_today": False,
    })
    return rows


# ---------------------------------------------------------------------------
# 1. Trend and seasonal cycle
# ---------------------------------------------------------------------------

def run_trend(bbox, label="Selected area"):
    """The whole XCO2 record for an area, split into trend/season/remainder.
    Ignores the user's date range on purpose — a trend needs the full record."""
    check = adequacy(bbox, "xco2_grid")
    if check["verdict"] == "too_small":
        return _too_small(check)

    start, end = SOURCES["xco2_grid"]["coverage"]
    try:
        rows = sources.xco2_series(bbox, start, end,
                                   step_days=TREND_SAMPLE_DAYS)
    except sources.SourceError as error:
        return _unavailable("Could not reach the data service", str(error))

    if not rows:
        return _unavailable(
            "No usable XCO2 days for this area",
            "Every day in the record either had no raster over this box or "
            "failed the plausibility check — a few days in this collection "
            f"are stored as all-zero files rather than as missing data, and "
            f"anything below {MIN_PLAUSIBLE_PPM:.0f} ppm is discarded.")

    parts = decompose(rows)
    if not parts:
        return _unavailable(
            "Not enough days to separate trend from season",
            f"Only {len(rows)} usable days came back. Splitting a series into "
            "a long-term rise and a yearly cycle needs at least "
            f"{MIN_YEARS_FOR_SEASONAL:.0f} full years of them.")

    return {"available": True, "label": label, "bbox": bbox,
            "adequacy": check, "source": "xco2_grid",
            "coverage": (start, end), "series": rows, **parts}


# ---------------------------------------------------------------------------
# 2. Deseasonalised anomaly against the surrounding box
# ---------------------------------------------------------------------------

def run_anomaly(bbox, label="Selected area"):
    """AOI vs. background box, each detrended/deseasonalised before
    differencing (raw difference isn't usable — see WHY_LAND_COVER)."""
    check = adequacy(bbox, "xco2_grid")
    if check["verdict"] == "too_small":
        return _too_small(check)

    background = context_bbox(bbox)
    start, end = SOURCES["xco2_grid"]["coverage"]
    try:
        aoi_rows = sources.xco2_series(bbox, start, end,
                                       step_days=TREND_SAMPLE_DAYS)
        bg_rows = sources.xco2_series(background, start, end,
                                      step_days=TREND_SAMPLE_DAYS)
    except sources.SourceError as error:
        return _unavailable("Could not reach the data service", str(error))

    result = anomaly_between(aoi_rows, bg_rows)
    if not result:
        return _unavailable(
            "Not enough matched days to compare the two boxes",
            "The area and its surrounding box have to be measured on the "
            "same days for the difference to mean anything, and fewer than "
            "eight such days came back.")

    level, colour = classify_anomaly(result["mean_anomaly"])
    return {"available": True, "label": label, "bbox": bbox,
            "background_bbox": background, "adequacy": check,
            "level": level, "level_color": colour, **result}


# ---------------------------------------------------------------------------
# 3. Fossil-fuel emissions inventory
# ---------------------------------------------------------------------------

def odiac_classes():
    """ODIAC's colour classes as titiler intervals, plus their CO2 labels.
    Breaks are in tonnes CO2; the raster stores carbon, so divided by 44/12 here."""
    carbon_breaks = [value / CARBON_TO_CO2 for value in ODIAC_CO2_BREAKS]
    edges = [0.0] + carbon_breaks + [1e9]
    intervals, labels = [], []
    for index, (colour, alpha) in enumerate(ODIAC_CLASS_COLORS):
        red = int(colour[1:3], 16)
        green = int(colour[3:5], 16)
        blue = int(colour[5:7], 16)
        intervals.append([[edges[index], edges[index + 1]],
                          [red, green, blue, alpha]])
        low = 0.0 if index == 0 else ODIAC_CO2_BREAKS[index - 1]
        high = (None if index == len(ODIAC_CLASS_COLORS) - 1
                else ODIAC_CO2_BREAKS[index])
        labels.append((low, high, colour))
    return intervals, labels


def run_inventory(bbox, date_start, date_end, label="Selected area"):
    """Where the CO2 is emitted, at 1 km, from ODIAC — a modelled emissions
    total spread over a grid, not an atmospheric measurement."""
    check = adequacy(bbox, "odiac")
    if check["verdict"] == "too_small":
        return _too_small(check)

    window = clamp_to_coverage("odiac", date_start, date_end)
    if not window:
        return _outside_coverage("odiac", date_start, date_end)

    try:
        found = sources.items("odiac", *window)
    except sources.SourceError as error:
        return _unavailable("Could not reach the data service", str(error))
    if not found:
        return _unavailable(
            "No inventory months in this window",
            f"ODIAC is monthly and covers "
            f"{SOURCES['odiac']['coverage'][0]} to "
            f"{SOURCES['odiac']['coverage'][1]}.")

    monthly = []
    for day, item_id in found:
        stats = sources.zonal_stats("odiac", item_id, bbox)
        totals = inventory_totals(stats, bbox)
        if totals:
            monthly.append({"date": day, "item": item_id, **totals})

    if not monthly:
        return _unavailable(
            "The inventory has no emitting cells inside this area",
            "ODIAC leaves cells with no fossil-fuel activity empty rather "
            "than setting them to zero, so a box entirely over wilderness or "
            "open water comes back with nothing in it.")

    latest = monthly[-1]
    return {
        "available": True, "label": label, "bbox": bbox, "adequacy": check,
        "window": window, "gap": coverage_gap("odiac", date_start, date_end),
        "monthly": monthly, "latest": latest,
        "tile_url": sources.tile_url("odiac", latest["item"],
                                     intervals=odiac_classes()[0]),
        "classes": odiac_classes()[1],
    }


# ---------------------------------------------------------------------------
# 4. Targeted snapshots
# ---------------------------------------------------------------------------

# Snapshot rasters use their own footprint/shape, not a fixed grid; shape is
# read from the service (sources.raster_shape) — this is only the fallback.
SAM_FALLBACK_CELLS = 800


def _cell_area_km2(footprint, shape=None):
    import math
    columns, rows = shape or (SAM_FALLBACK_CELLS, SAM_FALLBACK_CELLS)
    columns = columns or SAM_FALLBACK_CELLS
    rows = rows or SAM_FALLBACK_CELLS
    mid_lat = (footprint["N"] + footprint["S"]) / 2.0
    height = (footprint["N"] - footprint["S"]) / rows * 111.0
    width = ((footprint["E"] - footprint["W"]) / columns * 111.0
             * max(math.cos(math.radians(mid_lat)), 0.01))
    return height * width


def _footprint_km2(footprint):
    import math
    mid_lat = (footprint["N"] + footprint["S"]) / 2.0
    return ((footprint["N"] - footprint["S"]) * 111.0
            * (footprint["E"] - footprint["W"]) * 111.0
            * max(math.cos(math.radians(mid_lat)), 0.01))


def run_snapshots(bbox, date_start, date_end, label="Selected area"):
    """Real CO2 soundings over this area — where the satellite was aimed.
    No adequacy check: at ~2 km the constraint is whether a snapshot was
    ever taken here, not box size."""
    try:
        found = sources.search("sam", bbox)
    except sources.SourceError as error:
        return _unavailable("Could not reach the data service", str(error))

    # The collection also carries solar-induced fluorescence items; keep only CO2.
    co2_items = sorted((item for item in found
                        if item["id"].endswith("_xco2")),
                       key=lambda item: item["date"])
    if not co2_items:
        return _unavailable(
            "No targeted CO2 snapshot has ever been taken over this area",
            "OCO-2 and OCO-3 point at chosen targets — cities, power "
            "stations, industrial sites — rather than scanning continuously. "
            "Nowhere inside this box is on that target list, so there is "
            "nothing to show. Try a box around a major industrial site or a "
            "large city.")

    in_window = [item for item in co2_items
                 if date_start <= item["date"] <= date_end]
    chosen = (in_window or co2_items)[-1]

    try:
        footprint = sources.item_bbox("sam", chosen["id"])
        stats = sources.zonal_stats("sam", chosen["id"], footprint)
    except sources.SourceError as error:
        return _unavailable("Could not reach the data service", str(error))

    if not stats or stats.get("mean") is None:
        return _unavailable(
            "The snapshot over this area has no valid soundings",
            "A snapshot is stored even when cloud or aerosol rejected most "
            "of its soundings, and this one kept none inside the box.")

    low = (stats.get("percentile_2") or stats["min"]) - SAM_PAD_PPM
    high = (stats.get("percentile_98") or stats["max"]) + SAM_PAD_PPM

    # `count` is filled cells (~80x140 m), NOT soundings — the real footprint
    # is ~2 km, so one sounding paints several cells.
    try:
        shape = sources.raster_shape("sam", chosen["id"])
    except sources.SourceError:
        shape = None
    cell_km2 = _cell_area_km2(footprint, shape)
    return {
        "available": True, "label": label, "bbox": bbox,
        "all_items": co2_items, "in_window": in_window, "chosen": chosen,
        "used_out_of_window": not in_window,
        "requested": (date_start, date_end),
        "footprint": footprint, "stats": stats,
        "filled_cells": stats.get("count"),
        "raster_shape": shape,
        "covered_km2": (stats.get("count") or 0) * cell_km2,
        "footprint_km2": _footprint_km2(footprint),
        "spread": stats["max"] - stats["min"],
        "tile_url": sources.tile_url("sam", chosen["id"], (low, high),
                                     SAM_COLORMAP),
        "rescale": (low, high),
    }


# ---------------------------------------------------------------------------
# 5. Combustion CO2 inferred from NO2
# ---------------------------------------------------------------------------

def run_inferred(bbox, date_start, date_end, label="Selected area"):
    """What the observed NO2 implies about this area's combustion CO2 —
    an inference, not a measurement (see WHY_INFERRED)."""
    if date_end < NO2_COVERAGE_START:
        return _unavailable(
            "Sentinel-5P NO2 does not reach back this far",
            f"NO2 coverage starts {NO2_COVERAGE_START}. Pick a window after "
            f"that date.")
    start = max(date_start, NO2_COVERAGE_START)
    background = context_bbox(bbox)

    try:
        aoi = sources.no2_stats(bbox, start, date_end)
        bg = sources.no2_stats(background, start, date_end, background=True)
    except sources.SourceError as error:
        return _unavailable("Earth Engine could not answer", str(error))

    if not aoi or not bg:
        return _unavailable(
            "No NO2 pixels over this area in this window",
            "TROPOMI's NO2 retrieval is discarded under cloud and at very "
            "low sun angles, so a short winter window at high latitude can "
            "come back empty. Try a longer window or a summer one.")

    delta = aoi["mean"] - bg["mean"]
    inferred = infer_from_no2(delta)

    return {
        "available": True, "label": label, "bbox": bbox,
        "background_bbox": background, "window": (start, date_end),
        "clamped": start != date_start,
        "no2_aoi": aoi["mean"], "no2_background": bg["mean"],
        "no2_delta": delta, "no2_pixels": aoi.get("count"),
        "no2_pct": (100.0 * delta / bg["mean"]) if bg["mean"] else None,
        "inferred": inferred,
        "no_plume": inferred is None,
    }
