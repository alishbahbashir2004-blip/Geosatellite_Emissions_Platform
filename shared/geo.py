# shared/geo.py
# Location inputs -> bounding box, plus the geometry math hotspot segmentation
# needs. No gas, no band, no threshold.

import math

from shared.regions import REGIONS
from shared.cities import CITIES

CITY_PAD_DEG = 0.15        # ~15 km, enough to turn a city point into an AOI
METRES_PER_DEGREE = 111320.0

# Segmentation grid limits: shared across gases since CH4, CO, NO2 and SO2
# Sentinel-5P L3 products are all published on the same 0.01-degree grid.
HOTSPOT_MIN_SCALE = 1113.2   # metres: the 0.01-degree grid the assets use
HOTSPOT_MAX_CELLS = 160      # cells across AOI's longer side (caps vectorising cost)
HOTSPOT_MIN_CELLS = 4        # a patch must be a blob, not a one-cell streak


def lookup_city(name):
    """CITIES may be a dict (name -> meta) or a list of {name, lat, lon}."""
    if isinstance(CITIES, dict):
        return CITIES.get(name)
    if isinstance(CITIES, list):
        return next(
            (c for c in CITIES if isinstance(c, dict) and c.get("name") == name),
            None,
        )
    return None


def resolve_bbox(region_name=None, city_name=None, N=None, S=None, W=None,
                 E=None):
    """Turn any of the three location inputs into a bounding box.
    Returns (bbox_dict, error_message); exactly one of the two is None."""
    if region_name:
        box = REGIONS.get(region_name)
        if not box:
            return None, f"Unknown region: {region_name}"
        # Some entries in regions.py have W/E the wrong way round — normalise,
        # same as the raw N/S/W/E path below.
        return {"N": max(box["N"], box["S"]), "S": min(box["N"], box["S"]),
                "W": min(box["W"], box["E"]), "E": max(box["W"], box["E"])}, None

    if city_name:
        city = lookup_city(city_name)
        if not city:
            return None, f"Unknown city: {city_name}"
        # A city is a point, not a box — buffer it into a usable AOI.
        return {
            "N": city["lat"] + CITY_PAD_DEG,
            "S": city["lat"] - CITY_PAD_DEG,
            "W": city["lon"] - CITY_PAD_DEG,
            "E": city["lon"] + CITY_PAD_DEG,
        }, None

    if None in (N, S, W, E):
        return None, "Provide a region_name, city_name, or N/S/W/E."

    # Some entries in regions.py have W/E the wrong way round — normalise.
    return {"N": max(N, S), "S": min(N, S),
            "W": min(W, E), "E": max(W, E)}, None


def context_bbox(bbox):
    """Larger box around the AOI used as the 'local background' reference;
    padded by the AOI's own size, floored at a degree."""
    pad_lat = max(1.0, bbox["N"] - bbox["S"])
    pad_lon = max(1.0, bbox["E"] - bbox["W"])
    return {
        "N": min(90.0, bbox["N"] + pad_lat),
        "S": max(-90.0, bbox["S"] - pad_lat),
        "W": max(-180.0, bbox["W"] - pad_lon),
        "E": min(180.0, bbox["E"] + pad_lon),
    }


def bbox_of_ring(coords):
    """{N,S,W,E} of a GeoJSON polygon's outer ring."""
    ring = (coords[0] if coords and isinstance(coords[0][0], (list, tuple))
            else coords)
    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    return {"N": max(lats), "S": min(lats), "W": min(lons), "E": max(lons)}


def fill_pct(box, cells, scale):
    """Share of a patch's bounding box that the patch's own cells occupy.
    Low for an L-shaped/straggling patch, where the box is just a locator."""
    mid_lat = math.radians((box["N"] + box["S"]) / 2)
    height = (box["N"] - box["S"]) * METRES_PER_DEGREE
    width = ((box["E"] - box["W"]) * METRES_PER_DEGREE
             * max(math.cos(mid_lat), 0.05))
    box_cells = (max(height, scale) / scale) * (max(width, scale) / scale)
    if not box_cells:
        return None
    return min(100.0, 100.0 * cells / box_cells)


def hotspot_scale(bbox):
    """Segmentation cell size for this AOI, in metres: the asset's own grid,
    grown for a large AOI to keep the cell count bounded."""
    mid_lat = math.radians((bbox["N"] + bbox["S"]) / 2)
    span_m = max(
        (bbox["N"] - bbox["S"]) * METRES_PER_DEGREE,
        (bbox["E"] - bbox["W"]) * METRES_PER_DEGREE * max(math.cos(mid_lat), 0.05),
    )
    return max(HOTSPOT_MIN_SCALE, span_m / HOTSPOT_MAX_CELLS)


def min_patch_cells(scale, footprint_scale):
    """Smallest patch worth reporting, in segmentation cells: at least the
    sensor footprint (binds on fine grids) and at least a 2x2 blob (binds on
    coarse grids, else a province-sized AOI reports hundreds of 2-cell "regions")."""
    return max(HOTSPOT_MIN_CELLS, round((footprint_scale ** 2) / (scale ** 2)))
