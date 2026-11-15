# api/main.py
# The HTTP layer the React client talks to. Thin wrapper only: each route
# resolves a bbox, calls the same pipeline the Streamlit page called, and
# hands the result to api/render.py. If a number is wrong, it's wrong in a
# gas's backend, not here. Every route returns through ok() (see api/encode.py
# for why numpy needs the extra pass).
#
# Run: uvicorn api.main:app --reload --port 8000
# Dev: Vite dev server proxies /api here. Prod: built client served from
# web/dist by the catch-all at the bottom.

import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared.cities import CITIES
from shared.geo import resolve_bbox
from shared.regions import REGIONS
from api import co2_render, render
from api.encode import jsonable
from api.specs import S5P_KEYS, dashboard, descriptor, modules

app = FastAPI(title="Satellite Emissions Intelligence")

# Vite dev server is cross-origin to this one. Extra origins (e.g. a
# separately hosted client) come from ALLOWED_ORIGINS, comma-separated.
_extra_origins = [o.strip() for o in
                   os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   *_extra_origins],
    allow_methods=["*"], allow_headers=["*"],
)


def ok(payload):
    """A JSON response with numpy scalars converted and NaN sent as null."""
    return JSONResponse(content=jsonable(payload))


class Location(BaseModel):
    region_name: Optional[str] = None
    city_name: Optional[str] = None
    N: Optional[float] = None
    S: Optional[float] = None
    W: Optional[float] = None
    E: Optional[float] = None

    def label(self):
        return self.region_name or self.city_name or "Selected area"


class Query(Location):
    date_start: str
    date_end: str


class CompareQuery(BaseModel):
    areas: list[Query]
    selected: int = 0


def _gas(key):
    if key not in S5P_KEYS:
        raise HTTPException(404, f"Unknown gas: {key}")
    return modules(key)


def _bbox(location: Location):
    bbox, error = resolve_bbox(location.region_name, location.city_name,
                               location.N, location.S, location.W, location.E)
    if error:
        raise HTTPException(400, error)
    return bbox


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
def get_dashboard():
    return ok({"gases": dashboard()})


@app.get("/api/places")
def get_places():
    """Region boxes and city names, for the location picker."""
    cities = (sorted(CITIES.keys()) if isinstance(CITIES, dict)
              else sorted(c.get("name", str(c)) if isinstance(c, dict)
                          else str(c) for c in CITIES))
    return ok({"regions": REGIONS, "cities": cities})


@app.post("/api/resolve")
def post_resolve(location: Location):
    """The box a location input points at, before any query is run."""
    bbox = _bbox(location)
    return ok({"bbox": bbox, "label": location.label(),
               "map": render.preview_map(bbox, location.label())})


# ---------------------------------------------------------------------------
# The four Sentinel-5P gases
# ---------------------------------------------------------------------------

@app.get("/api/gas/{key}")
def get_gas(key: str):
    _gas(key)
    return ok(descriptor(key))


@app.post("/api/gas/{key}/run")
def post_gas_run(key: str, query: Query):
    """One area measured against the padded box around it."""
    parts = _gas(key)
    result = parts["backend"].run_pipeline(
        region_name=query.region_name, city_name=query.city_name,
        N=query.N, S=query.S, W=query.W, E=query.E,
        date_start=query.date_start, date_end=query.date_end)
    if result.get("error"):
        return ok({"error": result["error"], "label": query.label()})
    return ok({
        "error": None,
        "label": query.label(),
        "result": result,
        "charts": render.charts(key, result),
        "map": render.result_map(key, result),
        "levelLegend": parts["chartview"].level_legend_html(),
    })


@app.post("/api/gas/{key}/compare")
def post_gas_compare(key: str, query: CompareQuery):
    """Two areas of the same kind, read against each other."""
    parts = _gas(key)
    areas = []
    for area in query.areas:
        result = parts["backend"].run_pipeline(
            region_name=area.region_name, city_name=area.city_name,
            N=area.N, S=area.S, W=area.W, E=area.E,
            date_start=area.date_start, date_end=area.date_end)
        if result.get("error"):
            return ok({"error": f"{area.label()}: {result['error']}"})
        areas.append({"label": area.label(), "result": result,
                      "charts": render.charts(key, result)})
    return ok({
        "error": None,
        "areas": areas,
        "map": render.compare_map(key, areas, query.selected),
        "levelLegend": parts["chartview"].level_legend_html(),
    })


# ---------------------------------------------------------------------------
# CO2 — five analyses, each able to decline
# ---------------------------------------------------------------------------

@app.get("/api/co2")
def get_co2():
    """The CO2 page's static furniture: products, bands and the prose."""
    from co2 import config as c
    return ok({
        "sources": {key: {"label": source["label"], "unit": source["unit"],
                          "cadence": source["cadence"], "kind": source["kind"],
                          "coverage": source["coverage"],
                          "whatItIs": source["what_it_is"]}
                    for key, source in c.SOURCES.items()},
        "levels": [{"upper": None if upper == float("inf") else upper,
                    "label": label, "color": color}
                   for upper, label, color in c.ANOMALY_LEVELS],
        "levelUnit": c.LEVEL_UNIT,
        "levelTitle": c.LEVEL_TITLE,
        "accent": c.ACCENT,
        "no2CoverageStart": c.NO2_COVERAGE_START,
        "emissionRatios": c.EMISSION_RATIOS,
        "prose": {
            "trend": c.WHY_TREND,
            "seasonal": c.WHY_SEASONAL,
            "deseasonalise": c.WHY_DESEASONALISE,
            "landCover": c.WHY_LAND_COVER,
            "tooSmall": c.WHY_TOO_SMALL,
            "noEnhancement": c.WHY_NO_CO2_ENHANCEMENT,
            "inferred": c.WHY_INFERRED,
        },
    })


@app.post("/api/co2/coverage")
def post_co2_coverage(query: Query):
    from co2 import backend as co2_backend
    rows = co2_backend.coverage_timeline(query.date_start, query.date_end)
    return ok({"rows": rows,
               "chart": co2_render.coverage_chart(rows, query.date_start,
                                                  query.date_end)})


@app.post("/api/co2/trend")
def post_co2_trend(query: Query):
    from co2 import backend as co2_backend
    from co2.config import why_deseasonalise, why_seasonal
    bbox = _bbox(query)
    result = co2_backend.run_trend(bbox, query.label())
    if not result["available"]:
        grid = (co2_render.grid_map(bbox, "xco2_grid", result["adequacy"],
                                    label=query.label())
                if result.get("adequacy") else None)
        return ok({**result, "map": grid})
    return ok({
        **result,
        "charts": co2_render.trend_charts(result, query.date_start,
                                          query.date_end),
        "prose": {
            "seasonal": why_seasonal(result["label"],
                                     result["seasonal_amplitude"],
                                     result["seasonal_max_month"],
                                     result["seasonal_min_month"]),
            "deseasonalise": why_deseasonalise(result["label"],
                                               result["seasonal_amplitude"],
                                               result["slope_ppm_per_year"]),
        },
    })


@app.post("/api/co2/anomaly")
def post_co2_anomaly(query: Query):
    from co2 import backend as co2_backend
    bbox = _bbox(query)
    result = co2_backend.run_anomaly(bbox, query.label())
    if not result["available"]:
        return ok(result)
    return ok({**result,
               "charts": co2_render.anomaly_charts(result),
               "map": co2_render.grid_map(bbox, "xco2_grid",
                                          result["adequacy"],
                                          result["background_bbox"],
                                          query.label())})


@app.post("/api/co2/inventory")
def post_co2_inventory(query: Query):
    from co2 import backend as co2_backend
    bbox = _bbox(query)
    result = co2_backend.run_inventory(bbox, query.date_start, query.date_end,
                                       query.label())
    if not result["available"]:
        return ok(result)
    return ok({**result,
               "charts": co2_render.inventory_charts(result),
               "map": co2_render.inventory_map(result)})


@app.post("/api/co2/snapshots")
def post_co2_snapshots(query: Query):
    from co2 import backend as co2_backend
    bbox = _bbox(query)
    result = co2_backend.run_snapshots(bbox, query.date_start, query.date_end,
                                       query.label())
    if not result["available"]:
        return ok(result)
    return ok({**result,
               "charts": co2_render.snapshot_charts(result),
               "map": co2_render.snapshot_map(result)})


@app.post("/api/co2/inferred")
def post_co2_inferred(query: Query):
    from co2 import backend as co2_backend
    bbox = _bbox(query)
    result = co2_backend.run_inferred(bbox, query.date_start, query.date_end,
                                      query.label())
    if not result["available"]:
        return ok(result)
    return ok({**result,
               "charts": co2_render.inferred_charts(result),
               "map": co2_render.inferred_map(result)})


# ---------------------------------------------------------------------------
# The built client
# ---------------------------------------------------------------------------

DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "web", "dist")

if os.path.isdir(DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")),
              name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        """Every non-API path returns index.html, so client routing works."""
        return FileResponse(os.path.join(DIST, "index.html"))
