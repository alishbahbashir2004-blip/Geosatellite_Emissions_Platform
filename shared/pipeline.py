# shared/pipeline.py
# Two gas-agnostic EE passes: daily means from a period's satellite passes,
# and segmenting an AOI's above-threshold pixels into contiguous patches.
# Gas-specific parts come back via `value_key` and `describe`.

import ee
from collections import defaultdict

from shared.geo import bbox_of_ring, fill_pct, hotspot_scale, min_patch_cells
from shared.stats import feature_stat


def daily_stats(collection, aoi, band, scale, value_key):
    """Per-day mean and pixel availability, combining each day's several passes.

    Returns (series, availability): series is daily means; availability is
    per-date sample_count/valid_count/no_data_count."""
    def per_pass(image):
        # "box": same band, mask dropped, counts every pixel on the retrieval's own grid.
        stacked = image.addBands(image.unmask(0).rename("box"))
        stats = stacked.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.count(),
                                              sharedInputs=True),
            geometry=aoi, scale=scale, maxPixels=1e9, bestEffort=True,
        )
        return ee.Feature(None, {
            "date": image.date().format("YYYY-MM-dd"),
            "value": stats.get(f"{band}_mean"),
            "valid": stats.get(f"{band}_count"),
            "sample": stats.get("box_count"),
        })

    features = (
        ee.FeatureCollection(collection.map(per_pass))
        # Drops only passes that failed to reduce at all; zero-pixel passes still count.
        .filter(ee.Filter.notNull(["sample"]))
        .getInfo()["features"]
    )

    by_date = defaultdict(lambda: {"values": [], "valid": 0, "sample": 0})
    for feature in features:
        props = feature["properties"]
        day = by_date[props["date"]]
        if props.get("value") is not None:
            day["values"].append(props["value"])
        day["valid"] += props.get("valid") or 0
        day["sample"] += props.get("sample") or 0

    series, availability = [], []
    for date, day in sorted(by_date.items()):
        if day["values"]:
            series.append({"date": date,
                           value_key: sum(day["values"]) / len(day["values"])})
        availability.append({
            "date": date,
            "sample_count": day["sample"],
            "valid_count": day["valid"],
            "no_data_count": max(day["sample"] - day["valid"], 0),
        })
    return series, availability


def hotspot_regions(mean_image, aoi, bbox, threshold, footprint_scale,
                    max_regions, describe):
    """Contiguous above-threshold patches of the AOI, each its own bounding box
    (segmented rather than one box, since hot pixels are usually scattered).

    Returns (regions, total_found): the hottest `max_regions` patches as
    {N,S,W,E, pixel_count, fill_pct, **describe(patch_mean, patch_max)},
    plus how many patches passed the size filter in total."""
    if threshold is None:
        return None, 0

    scale = hotspot_scale(bbox)
    min_cells = min_patch_cells(scale, footprint_scale)

    # First band is reduceToVectors' segmentation label; the gas band rides along for stats.
    mask = mean_image.gt(threshold).selfMask().rename("hot").toInt()
    vectors = mask.addBands(mean_image).reduceToVectors(
        reducer=(ee.Reducer.mean()
                 .combine(ee.Reducer.max(), sharedInputs=True)
                 .combine(ee.Reducer.count(), sharedInputs=True)),
        # "bb" is EE's spelling for a bounding box; "bbox" is rejected.
        geometry=aoi, scale=scale, geometryType="bb",
        eightConnected=True, labelProperty="label",
        maxPixels=1e9, bestEffort=True,
    )

    features = vectors.getInfo().get("features") or []

    # (sort key, region) pairs; ranking uses the raw patch mean, not describe()'s output.
    found = []
    for feature in features:
        geometry = (feature.get("geometry") or {}).get("coordinates")
        if not geometry:
            continue
        props = feature.get("properties") or {}
        patch_mean = feature_stat(props, "mean")
        if patch_mean is None:
            continue
        region = bbox_of_ring(geometry)
        cells = feature_stat(props, "count") or 0
        region["pixel_count"] = cells
        # Share of the drawn box actually above the cut.
        region["fill_pct"] = fill_pct(region, cells, scale)
        region.update(describe(patch_mean, feature_stat(props, "max")))
        found.append((patch_mean, region))

    # Drop speckle; if every patch is sub-footprint, keep the biggest rather than report none.
    solid = [pair for pair in found if pair[1]["pixel_count"] >= min_cells]
    if not solid and found:
        solid = [max(found, key=lambda pair: pair[1]["pixel_count"])]

    solid.sort(key=lambda pair: pair[0], reverse=True)
    return [region for _, region in solid[:max_regions]], len(solid)
