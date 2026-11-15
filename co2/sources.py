# co2/sources.py
# CO2's data layer (not in Earth Engine) — mirrors shared/earthengine.py but
# hits NASA's GHG Center instead; no2_stats() is this page's one EE call.

import json
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from co2.config import (STAC_API, RASTER_API, SOURCES, MIN_PLAUSIBLE_PPM,
                        NO2_ASSET, NO2_BAND, NO2_UNIT_SCALE, NO2_REDUCE_SCALE,
                        NO2_BACKGROUND_SCALE)

TIMEOUT = 90
MAX_WORKERS = 12


class SourceError(RuntimeError):
    """The service could not answer. Carries text meant for the page."""


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SourceError(f"The GHG Center catalogue returned "
                          f"{error.code} for this query.") from error
    except Exception as error:
        raise SourceError("Could not reach the GHG Center catalogue "
                          "(earth.gov). Check the network and retry.") from error


def _post(url, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise SourceError(f"The GHG Center raster service returned "
                          f"{error.code} for this area.") from error
    except Exception as error:
        raise SourceError("Could not reach the GHG Center raster service "
                          "(earth.gov). Check the network and retry.") from error


def as_polygon(bbox):
    """{N,S,W,E} -> the GeoJSON Feature the statistics endpoint wants."""
    west, south = bbox["W"], bbox["S"]
    east, north = bbox["E"], bbox["N"]
    return {"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[west, south], [east, south],
                                          [east, north], [west, north],
                                          [west, south]]]}}


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def items(source_key, date_start, date_end):
    """Item ids and dates for a collection in a window, oldest first.
    Fetched a year at a time — the endpoint 500s on a multi-year window."""
    source = SOURCES[source_key]
    found = []
    for year in range(int(date_start[:4]), int(date_end[:4]) + 1):
        low = max(f"{year}-01-01", date_start)
        high = min(f"{year}-12-31", date_end)
        if low > high:
            continue
        url = (f"{STAC_API}/collections/{source['collection']}/items"
               f"?limit=400&datetime={low}T00:00:00Z/{high}T23:59:59Z")
        for feature in _get(url)["features"]:
            found.append((_item_date(feature), feature["id"]))
    return sorted(set(found))


def _item_date(feature):
    """The date of an item, whichever way the collection spells it (daily:
    `datetime`; monthly inventory: `start_datetime`/`end_datetime` only)."""
    properties = feature.get("properties") or {}
    stamp = (properties.get("datetime")
             or properties.get("start_datetime")
             or properties.get("end_datetime") or "")
    return stamp[:10]


def search(source_key, bbox, limit=200):
    """Items of a collection whose footprint intersects a box — for targeted
    snapshots, where existence (not date) is the first question."""
    source = SOURCES[source_key]
    payload = {"collections": [source["collection"]],
               "bbox": [bbox["W"], bbox["S"], bbox["E"], bbox["N"]],
               "limit": limit}
    features = _post(f"{STAC_API}/search", payload).get("features") or []
    return [{"id": feature["id"], "date": _item_date(feature),
             "bbox": feature.get("bbox")} for feature in features]


def item_bbox(source_key, item_id):
    source = SOURCES[source_key]
    feature = _get(f"{STAC_API}/collections/{source['collection']}"
                   f"/items/{item_id}")
    west, south, east, north = feature["bbox"][:4]
    return {"N": north, "S": south, "W": west, "E": east}


# ---------------------------------------------------------------------------
# Statistics — reduceRegion, over HTTP
# ---------------------------------------------------------------------------

def zonal_stats(source_key, item_id, bbox):
    """Statistics for one raster over one box, or None if it has nothing there.
    `count` is cells read, not cells that exist (the endpoint resamples a
    large box down) — fine for means/percentiles, why nothing here sums."""
    source = SOURCES[source_key]
    url = (f"{RASTER_API}/collections/{source['collection']}"
           f"/items/{item_id}/statistics?assets={source['asset']}")
    try:
        response = _post(url, as_polygon(bbox))
    except SourceError:
        return None
    stats = (response.get("properties") or {}).get("statistics") or {}
    for key, value in stats.items():
        if key.startswith(source["asset"]):
            return value
    return None


def raster_shape(source_key, item_id):
    """(width, height) of one raster, in cells — asked rather than assumed,
    since covered-area = cell_count x cell_area would be silently wrong otherwise."""
    source = SOURCES[source_key]
    info = _get(f"{RASTER_API}/collections/{source['collection']}"
                f"/items/{item_id}/info?assets={source['asset']}")
    info = info.get(source["asset"], info)
    return info.get("width"), info.get("height")


def series(source_key, bbox, date_start, date_end, step_days=1,
           drop_below=None):
    """[{date, mean, std, min, max, count}] for a box over a period.
    `drop_below` discards days under a plausibility floor — some XCO2 days
    are all-zero rasters, not masked nodata, which would fabricate a cycle."""
    found = items(source_key, date_start, date_end)[::step_days]
    if not found:
        return []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        stats = list(pool.map(
            lambda pair: zonal_stats(source_key, pair[1], bbox), found))

    rows = []
    for (day, _), stat in zip(found, stats):
        if not stat or stat.get("mean") is None:
            continue
        if drop_below is not None and stat["mean"] < drop_below:
            continue
        rows.append({"date": day, "mean": stat["mean"],
                     "std": stat.get("std"), "min": stat.get("min"),
                     "max": stat.get("max"), "count": stat.get("count")})
    return rows


def xco2_series(bbox, date_start, date_end, step_days=1):
    """The gridded XCO2 series, with the all-zero days already dropped."""
    return series("xco2_grid", bbox, date_start, date_end,
                  step_days=step_days, drop_below=MIN_PLAUSIBLE_PPM)


# ---------------------------------------------------------------------------
# Tiles — the map layer, coloured before it reaches the browser
# ---------------------------------------------------------------------------

def tile_url(source_key, item_id, rescale=None, colormap=None,
             intervals=None):
    """An XYZ tile template for one raster, coloured server-side via a query
    param. `rescale`+`colormap`: linear stretch (XCO2). `intervals`: explicit
    classes, for ODIAC (spans orders of magnitude; a ramp would flatten it)."""
    source = SOURCES[source_key]
    base = (f"{RASTER_API}/collections/{source['collection']}"
            f"/items/{item_id}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}@1x"
            f"?assets={source['asset']}")
    if intervals is not None:
        return f"{base}&colormap={urllib.parse.quote(json.dumps(intervals))}"
    low, high = rescale
    return f"{base}&rescale={low},{high}&colormap_name={colormap}"


# ---------------------------------------------------------------------------
# Sentinel-5P NO2, for the inferred analysis
# ---------------------------------------------------------------------------

def no2_stats(bbox, date_start, date_end, background=False):
    """Mean/std/count of TROPOMI NO2 over a box, in umol/m2. Must match
    no2/backend.py exactly (band, filterBounds, reduction scale: 5500m AOI /
    15000m background) or this page quietly disagrees with the NO2 page."""
    import ee
    from shared.earthengine import init as ee_init

    try:
        ee_init()
        region = ee.Geometry.Rectangle([bbox["W"], bbox["S"],
                                        bbox["E"], bbox["N"]])
        collection = (ee.ImageCollection(NO2_ASSET).select(NO2_BAND)
                      .filterDate(date_start, date_end)
                      .filterBounds(region))
        image = collection.mean().multiply(NO2_UNIT_SCALE)
        reducer = (ee.Reducer.mean()
                   .combine(ee.Reducer.stdDev(), sharedInputs=True)
                   .combine(ee.Reducer.count(), sharedInputs=True))
        stats = image.reduceRegion(
            reducer=reducer, geometry=region,
            scale=(NO2_BACKGROUND_SCALE if background else NO2_REDUCE_SCALE),
            maxPixels=1e9, bestEffort=True).getInfo()
    except Exception as error:
        raise SourceError(f"Earth Engine could not return NO2 for this area: "
                          f"{error}") from error

    mean = stats.get(f"{NO2_BAND}_mean")
    if mean is None:
        return None
    return {"mean": mean, "std": stats.get(f"{NO2_BAND}_stdDev"),
            "count": stats.get(f"{NO2_BAND}_count")}
