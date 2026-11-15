# co2/explore.py
# Dev-only script: checks whether the other gases' AOI-vs-background method
# holds up for CO2, using real data over the same boxes/dates as CH4 and NO2.
#
#   CH4, NO2   Earth Engine, COPERNICUS/S5P/OFFL/L3_*        (raster, daily)
#   XCO2       NASA GHG Center STAC + raster API              (no login needed)
#
# Run it:  python -m co2.explore        (from the app root)
# Writes:  co2/explore_cache.json, co2/why_co2_is_different.png

import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "explore_cache.json")
FIGURE = os.path.join(HERE, "why_co2_is_different.png")

STAC = "https://earth.gov/ghgcenter/api/stac"
RASTER = "https://earth.gov/ghgcenter/api/raster"
GRID = "oco2geos-co2-daygrid-v10r"      # assimilated daily XCO2, ~0.5 x 0.625 deg
SAMS = "oco3-co2-sams-daygrid-v11r"     # targeted snapshots, ~2 km

# The same geometry the app uses: regions.py boxes, cities buffered by
# CITY_PAD_DEG, backgrounds padded the way geo.context_bbox pads them.
BOXES = {
    "Alberta":     {"N": 60.0000, "S": 49.0000, "W": -120.0000, "E": -110.0000},
    "Alberta_bg":  {"N": 71.0000, "S": 38.0000, "W": -130.0000, "E": -100.0000},
    "Edmonton":    {"N": 53.6961, "S": 53.3961, "W": -113.6409, "E": -113.3409},
    "Edmonton_bg": {"N": 54.6961, "S": 52.3961, "W": -114.6409, "E": -112.3409},
}

DETAIL_MONTH = ("2021-07-01", "2021-07-31")   # one month, all three gases
TREND_YEARS = ("2015-01-01", "2022-02-28")    # the grid product's whole life
TREND_STEP_DAYS = 7


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def as_polygon(box):
    w, s, e, n = box["W"], box["S"], box["E"], box["N"]
    return {"type": "Feature", "properties": {},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[w, s], [e, s], [e, n],
                                          [w, n], [w, s]]]}}


def post_json(url, payload, timeout=90):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request, timeout=timeout))


def get_json(url, timeout=90):
    return json.load(urllib.request.urlopen(url, timeout=timeout))


# ---------------------------------------------------------------------------
# XCO2 out of the GHG Center
# ---------------------------------------------------------------------------

def xco2_stats(collection, item_id, box, asset):
    """Zonal statistics for one day's XCO2 raster over one box.

    The same operation as Earth Engine's reduceRegion, done by a titiler
    service instead: it reads only the window of the cloud-optimised GeoTIFF
    that the polygon touches, so nothing is downloaded whole.
    """
    url = (f"{RASTER}/collections/{collection}/items/{item_id}"
           f"/statistics?assets={asset}")
    try:
        response = post_json(url, as_polygon(box))
    except Exception:
        return None
    stats = response["properties"]["statistics"]
    return stats.get(f"{asset}_b1")


def grid_items(start, end, step_days=1):
    """Daily XCO2 item ids in a window, thinned to every `step_days`.

    Fetched a year at a time: the STAC endpoint answers a few hundred items
    happily and returns a 500 when asked for a seven-year window at once.
    """
    dated = []
    for year in range(int(start[:4]), int(end[:4]) + 1):
        lo = max(f"{year}-01-01", start)
        hi = min(f"{year}-12-31", end)
        url = (f"{STAC}/collections/{GRID}/items"
               f"?limit=400&datetime={lo}T00:00:00Z/{hi}T23:59:59Z")
        dated += [(f["properties"]["datetime"][:10], f["id"])
                  for f in get_json(url)["features"]]
    return sorted(set(dated))[::step_days]


# XCO2 in the real atmosphere has never been below ~250 ppm in the ice-core
# record and sits near 420 today, so anything under this is not a measurement.
# It matters: a handful of days in this collection are written as all-zero
# rasters rather than as masked nodata, and the statistics service counts
# those zeros as valid pixels. One such day (2017-06-16) is enough to drag
# June's seasonal mean down by 7 ppm and invent a cycle that is not there.
MIN_PLAUSIBLE_PPM = 300.0


def xco2_series(start, end, box, step_days=1):
    """[(date, mean, std, pixel_count)] for a box over a period.

    Days whose raster is all-zero nodata are dropped — see MIN_PLAUSIBLE_PPM.
    """
    items = grid_items(start, end, step_days)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(
            lambda pair: xco2_stats(GRID, pair[1], box, "xco2"), items))
    return [(day, r["mean"], r["std"], r["count"])
            for (day, _), r in zip(items, results)
            if r and r["mean"] > MIN_PLAUSIBLE_PPM]


# ---------------------------------------------------------------------------
# CH4 and NO2 out of Earth Engine
# ---------------------------------------------------------------------------

def s5p_stats(asset, band, unit_scale, footprint_m, box, start, end):
    """Mean/std/range of a Sentinel-5P band over a box, the app's own way."""
    import ee
    from shared.earthengine import init as ee_init
    ee_init()
    image = (ee.ImageCollection(asset).select(band)
             .filterDate(start, end).mean().multiply(unit_scale))
    reducer = (ee.Reducer.mean()
               .combine(ee.Reducer.stdDev(), sharedInputs=True)
               .combine(ee.Reducer.minMax(), sharedInputs=True)
               .combine(ee.Reducer.count(), sharedInputs=True))
    stats = image.reduceRegion(
        reducer=reducer,
        geometry=ee.Geometry.Rectangle([box["W"], box["S"], box["E"], box["N"]]),
        scale=footprint_m, maxPixels=1e9, bestEffort=True).getInfo()
    return {"mean": stats.get(f"{band}_mean"), "std": stats.get(f"{band}_stdDev"),
            "min": stats.get(f"{band}_min"), "max": stats.get(f"{band}_max"),
            "count": stats.get(f"{band}_count")}


S5P = {
    "CH4": ("COPERNICUS/S5P/OFFL/L3_CH4",
            "CH4_column_volume_mixing_ratio_dry_air", 1.0, 7000, "ppb"),
    "NO2": ("COPERNICUS/S5P/OFFL/L3_NO2",
            "NO2_column_number_density", 1e6, 5500, "µmol/m²"),
}


# ---------------------------------------------------------------------------
# Gather
# ---------------------------------------------------------------------------

def gather():
    if os.path.exists(CACHE):
        print(f"reading {CACHE} (delete it to refetch)")
        with open(CACHE) as handle:
            return json.load(handle)

    data = {"detail": {}, "trend": {}, "sam": {}}
    start, end = DETAIL_MONTH

    print("Sentinel-5P (Earth Engine) ...")
    for gas, (asset, band, scale, metres, unit) in S5P.items():
        data["detail"][gas] = {"unit": unit, "boxes": {}}
        for name, box in BOXES.items():
            data["detail"][gas]["boxes"][name] = s5p_stats(
                asset, band, scale, metres, box, start, f"{end}T23:59:59")
            print(f"  {gas} {name}")

    print("XCO2 gridded (GHG Center) ...")
    data["detail"]["CO2"] = {"unit": "ppm", "boxes": {}}
    for name, box in BOXES.items():
        series = xco2_series(start, end, box)
        means = [row[1] for row in series]
        data["detail"]["CO2"]["boxes"][name] = {
            "mean": float(np.mean(means)),
            "std": float(np.mean([row[2] for row in series])),
            "min": float(np.min(means)), "max": float(np.max(means)),
            "count": series[0][3],
        }
        print(f"  CO2 {name}  ({len(series)} days)")

    print(f"XCO2 trend {TREND_YEARS[0]}..{TREND_YEARS[1]} "
          f"(every {TREND_STEP_DAYS}d) ...")
    data["trend"]["Alberta"] = xco2_series(
        *TREND_YEARS, BOXES["Alberta"], TREND_STEP_DAYS)
    print(f"  {len(data['trend']['Alberta'])} points")

    print("Targeted snapshot over the oil sands ...")
    found = post_json(f"{STAC}/search", {
        "collections": [SAMS],
        "bbox": [-113, 55.5, -110, 58],
        "limit": 100,
    })["features"]
    co2_sams = sorted((f["properties"]["datetime"][:10], f["id"])
                      for f in found if f["id"].endswith("_xco2"))
    if co2_sams:
        day, item_id = co2_sams[-1]
        detail = get_json(f"{STAC}/collections/{SAMS}/items/{item_id}")
        box = {"W": detail["bbox"][0], "S": detail["bbox"][1],
               "E": detail["bbox"][2], "N": detail["bbox"][3]}
        data["sam"] = {"id": item_id, "date": day, "bbox": detail["bbox"],
                       "stats": xco2_stats(SAMS, item_id, box, "cog_default")}
        print(f"  {item_id}")

    with open(CACHE, "w") as handle:
        json.dump(data, handle, indent=1)
    return data


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def enhancement_table(data):
    print("\n" + "=" * 78)
    print("ONE BOX, ONE MONTH (July 2021), THREE GASES")
    print("The app's method: AOI mean minus padded-background mean.")
    print("=" * 78)
    for area in ("Edmonton", "Alberta"):
        print(f"\n  {area}")
        print(f"    {'gas':5s} {'AOI':>12s} {'background':>12s} "
              f"{'enhancement':>12s} {'% of bg':>9s} {'signal/noise':>13s}")
        for gas in ("CH4", "NO2", "CO2"):
            entry = data["detail"][gas]
            aoi = entry["boxes"][area]
            bg = entry["boxes"][f"{area}_bg"]
            rise = aoi["mean"] - bg["mean"]
            print(f"    {gas:5s} {aoi['mean']:12.3f} {bg['mean']:12.3f} "
                  f"{rise:+12.3f} {100 * rise / bg['mean']:8.3f}% "
                  f"{rise / aoi['std']:13.2f}   {entry['unit']}")
    print("\n  'signal/noise' is the enhancement divided by the spread of "
          "values\n  inside the AOI itself. Below ~1 the area is not "
          "distinguishable\n  from its own internal variation.")


def sampling_table(data):
    print("\n" + "=" * 78)
    print("HOW MANY MEASUREMENTS EACH BOX ACTUALLY CONTAINS")
    print("=" * 78)
    print(f"    {'gas':5s} {'Edmonton':>12s} {'Alberta':>12s}")
    for gas in ("CH4", "NO2", "CO2"):
        boxes = data["detail"][gas]["boxes"]
        print(f"    {gas:5s} {boxes['Edmonton']['count']:12.0f} "
              f"{boxes['Alberta']['count']:12.0f}")
    print("\n  Edmonton's AOI is 0.3 deg square. The XCO2 grid cell is "
          "0.5 x 0.625 deg,\n  so the city is smaller than one pixel and its "
          "'mean' is an interpolation.")


def trend_facts(data):
    series = data["trend"]["Alberta"]
    days = np.array([(date.fromisoformat(d) - date(2015, 1, 1)).days
                     for d, *_ in series], dtype=float)
    values = np.array([m for _, m, *_ in series])
    slope, intercept = np.polyfit(days, values, 1)
    residual = values - (slope * days + intercept)

    # Seasonal shape as each year's monthly mean minus that year's own mean.
    # Subtracting a straight line instead would leave the curvature of the
    # rise inside the "seasonal" term, since CO2 is accelerating, not linear.
    months = np.array([int(d[5:7]) for d, *_ in series])
    years = np.array([int(d[:4]) for d, *_ in series])
    yearly = []
    for year in sorted(set(years)):
        rows = np.array([values[(years == year) & (months == m)].mean()
                         if ((years == year) & (months == m)).any() else np.nan
                         for m in range(1, 13)])
        if np.isnan(rows).sum() > 2:      # a part-year at either end
            continue
        yearly.append(rows - np.nanmean(rows))
    by_month = np.nanmean(np.array(yearly), axis=0)
    del residual

    print("\n" + "=" * 78)
    print("WHAT MOVES CO2 OVER ALBERTA, IN ORDER OF SIZE")
    print("=" * 78)
    print(f"    long-term rise            {slope * 365.25:+6.2f} ppm / year")
    print(f"    seasonal swing            {by_month.max() - by_month.min():6.2f} "
          f"ppm peak to trough")
    print(f"      high in {date(2000, int(np.argmax(by_month)) + 1, 1):%B}, "
          f"low in {date(2000, int(np.argmin(by_month)) + 1, 1):%B}")
    edmonton = data["detail"]["CO2"]["boxes"]
    city = edmonton["Edmonton"]["mean"] - edmonton["Edmonton_bg"]["mean"]
    print(f"    Edmonton vs surroundings  {city:+6.3f} ppm")
    print(f"\n  The seasonal cycle is ~{abs((by_month.max() - by_month.min()) / city):.0f}x "
          f"the city signal, and the yearly rise\n  is "
          f"~{abs(slope * 365.25 / city):.0f}x. Neither has anything to do "
          f"with Alberta's industry:\n  it is the boreal forest inhaling in "
          f"summer and exhaling in winter,\n  on top of the global trend.")
    return slope, by_month, series


def sam_facts(data):
    sam = data.get("sam")
    if not sam or not sam.get("stats"):
        print("\n  (no targeted snapshot found over the oil sands box)")
        return
    stats = sam["stats"]
    print("\n" + "=" * 78)
    print("WHAT A TARGETED SNAPSHOT LOOKS LIKE INSTEAD")
    print("=" * 78)
    print(f"    {sam['id']}")
    print(f"    {sam['date']}, ~1 deg box over the Athabasca oil sands")
    print(f"    soundings {stats['count']:.0f}   mean {stats['mean']:.2f} ppm"
          f"   spread {stats['max'] - stats['min']:.2f} ppm"
          f"   std {stats['std']:.2f}")
    print("\n  Same instrument family, pointed rather than scanning. One pass "
          "gives\n  more measurements over one industrial site than the "
          "gridded product\n  gives over the whole province in a month.")


def figure(data, slope, by_month, series):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 9))
    fig.suptitle("Why CO2 cannot reuse the other four gases' pipeline",
                 fontsize=14, y=0.98)

    # (a) enhancement as a share of background
    ax = axes[0][0]
    gases = ("NO2", "CH4", "CO2")
    pct = []
    for gas in gases:
        boxes = data["detail"][gas]["boxes"]
        rise = boxes["Edmonton"]["mean"] - boxes["Edmonton_bg"]["mean"]
        pct.append(100 * rise / boxes["Edmonton_bg"]["mean"])
    bars = ax.bar(gases, pct, color=["#8e6bbf", "#d32f2f", "#2e7d32"])
    ax.set_yscale("symlog", linthresh=0.001)
    ax.set_ylabel("Edmonton above its surroundings (% of background)")
    ax.set_title("(a) The same city, three gases, July 2021")
    ax.axhline(0, color="#666", lw=0.8)
    for bar, value in zip(bars, pct):
        ax.text(bar.get_x() + bar.get_width() / 2, value,
                f"{value:+.3f}%", ha="center",
                va="bottom" if value > 0 else "top", fontsize=9)

    # (b) how many measurements
    ax = axes[0][1]
    counts = [data["detail"][g]["boxes"]["Edmonton"]["count"] for g in gases]
    ax.bar(gases, counts, color=["#8e6bbf", "#d32f2f", "#2e7d32"])
    ax.set_yscale("log")
    ax.set_ylabel("measurements inside the Edmonton AOI (log)")
    ax.set_title("(b) How much data is actually in the box")
    for index, value in enumerate(counts):
        ax.text(index, value, f"{value:,.0f}", ha="center", va="bottom",
                fontsize=9)

    # (c) the series itself
    ax = axes[1][0]
    days = [date.fromisoformat(d) for d, *_ in series]
    values = [m for _, m, *_ in series]
    ax.plot(days, values, lw=0.9, color="#2e7d32")
    line = np.poly1d(np.polyfit(
        [(d - date(2015, 1, 1)).days for d in days], values, 1))
    ax.plot(days, [line((d - date(2015, 1, 1)).days) for d in days],
            "--", color="#c62828", lw=1.2,
            label=f"trend {slope * 365.25:+.2f} ppm/yr")
    boxes = data["detail"]["CO2"]["boxes"]
    city = boxes["Edmonton"]["mean"] - boxes["Edmonton_bg"]["mean"]
    ax.annotate(f"Edmonton's entire signal: {city:+.3f} ppm\n"
                f"(about the width of this line)",
                xy=(days[len(days) // 2], values[len(days) // 2]),
                xytext=(0.06, 0.82), textcoords="axes fraction", fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#444", lw=0.9))
    ax.set_ylabel("XCO2 over Alberta (ppm)")
    ax.set_title("(c) What CO2 over Alberta actually does")
    ax.legend(loc="lower right", fontsize=8)

    # (d) seasonal shape after the trend is removed
    ax = axes[1][1]
    ax.bar(range(1, 13), by_month, color="#2e7d32")
    ax.axhline(0, color="#666", lw=0.8)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(list("JFMAMJJASOND"))
    ax.set_ylabel("ppm above / below the trend line")
    ax.set_title("(d) The biosphere, not industry: the seasonal cycle")
    # No band is drawn for the city signal on purpose: at 0.014 ppm it is
    # roughly 1/300th of the shortest bar here and would not render.
    ax.text(0.5, 0.06,
            f"Edmonton's whole-city signal is {city:+.3f} ppm —\n"
            f"~1/{abs(by_month.max() / city):.0f} of the shortest bar. "
            f"It cannot be drawn on this axis.",
            transform=ax.transAxes, ha="center", fontsize=8.5, color="#c62828")

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIGURE, dpi=140)
    print(f"\nwrote {FIGURE}")


if __name__ == "__main__":
    data = gather()
    enhancement_table(data)
    sampling_table(data)
    slope, by_month, series = trend_facts(data)
    sam_facts(data)
    figure(data, slope, by_month, series)
