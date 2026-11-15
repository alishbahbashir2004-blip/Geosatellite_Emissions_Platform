# Satellite Emissions Intelligence

Per-gas agents over satellite atmospheric data. Four of them — CH4, CO, NO2,
SO2 — read Sentinel-5P/TROPOMI through Earth Engine and measure an area
against a padded box around it over the same dates, reporting whether the
area stands above its own local background rather than against a global
average.

The fifth, CO2, does not, and cannot: see *The exception: CO2* below.

## Two front ends, one set of backends

The analysis lives in Python and is shared. There are two ways to look at it.

**React (the current one).** A FastAPI layer exposes the gas pipelines over
HTTP; a Vite/React SPA renders them.

```bash
uvicorn api.main:app --reload --port 8000     # also serves web/dist at /
```

To work on the client itself, run the dev server alongside it — Vite proxies
`/api` to uvicorn, so the client is written as if the two were one origin:

```bash
cd web && npm install && npm run dev          # http://localhost:5173
```

and `npm run build` when you are done, which is what uvicorn serves at `/`.

**Streamlit (the original).** Still works, untouched, against the same
backends:

```bash
streamlit run app.py
```

The dashboard opens first either way. Pick a gas and the router hands over to
that gas's own page.

### How the React port avoided rewriting anything that matters

Two decisions did most of the work:

- **Charts are not reimplemented.** Altair *is* Vega-Lite — `chart.to_dict()`
  is already the JSON a browser renders — so every figure is served as a spec
  and drawn by vega-embed. Retuning a chart still means editing that gas's
  `chartview.py` and nothing else.
- **Maps are described, not drawn.** Folium is Leaflet with a Python wrapper,
  so `api/render.py` emits the layers, rectangles and colour bar as data and
  react-leaflet draws them. The gas-specific parts — palette, layer names,
  tooltip wording — are still resolved server-side from that gas's `MapSpec`.

The four Sentinel-5P gases return the same state shape, so one React component
(`GasPage.tsx`) serves all four, driven by a descriptor assembled from each
gas's own config. CO2 has its own page, for the same reason it has its own
backend.

```
api/                the HTTP layer — no analysis, no thresholds, no wording
  specs.py            per-gas descriptors, read from each gas's own modules
  render.py           results -> Vega-Lite specs and map descriptions
  co2_render.py       the same for CO2's four map kinds
  encode.py           numpy -> JSON, so a np.bool_ is not a 500
  main.py             the routes

web/                the React client
  src/api.ts          the only place that talks to the server
  src/components/     VegaChart, ResultMap, LocationPicker, small UI pieces
  src/pages/          Dashboard, GasPage (all four S5P gases), Co2Page
```

## Layout

```
app.py              router — maps gases to pages, runs one, draws the sidebar
gas_registry.py     the one place a gas is declared
dashboard.py        landing page: a card per gas, built from the registry

shared/             everything that is true for every gas
  regions.py          reference data: named bounding boxes
  cities.py           reference data: city points
  earthengine.py      EE session, map tiles
  geo.py              region/city/coords -> bbox, background box, patch geometry
  pipeline.py         daily means from a period's passes; hotspot segmentation
  stats.py            EE histogram -> chart rows, box-plot summary
  levels.py           the level-table convention: classify + colour key
  charts.py           the four figures every gas page draws
  mapview.py          the Folium map every gas page draws
  chooser.py          the card grid a gas page opens on
  ui.py               metric formatting, the above/below-background line
  globeview.py        the spinning globe the map slot shows between queries
  earth_texture.jpg   its texture

ch4/                CH4 agent, self-contained
  config.py           every CH4-specific decision: product, unit, thresholds
  backend.py          pipeline
  mapview.py          map — palette, layer names, tooltip wording
  chartview.py        charts — how CH4's numbers are named and printed
  frontend.py         what the router runs: page config, then dispatch
  home.py             the landing cards — what would you like to do?
  single_area.py      one area measured against its surroundings
  compare.py          two areas of the same kind, read against each other

co/                 CO agent, the same eight files

no2/                NO2 agent — single-area only, so frontend.py is the page
  config.py           every NO2-specific decision
  backend.py          pipeline
  mapview.py          map
  chartview.py        charts
  frontend.py         page

so2/                SO2 agent, the same five files

co2/                CO2 agent — deliberately NOT the same files. See below.
  NOTES.md            why it differs, with the measurements behind it
  config.py           products, coverage windows, thresholds, and the prose
  sources.py          the data layer: STAC + raster API over HTTP, not EE
  analysis.py         adequacy checks, trend/season decomposition, inference
  backend.py          five analyses, each free to refuse and say why
  chartview.py        its own charts
  mapview.py          its own maps
  frontend.py         the page: five tabs, one per analysis
  explore.py          a runnable argument for all of the above
```

The rule that keeps the gases independent: **a gas folder imports `shared`
and nothing else of the app's, never another gas.** Nothing in `ch4/` is
imported by `co/` or the other way round, and adding a gas cannot break an
existing one.

## The exception: CO2

CO2 follows the folder rule — it imports `shared` and no other gas — and
breaks every other pattern here, because the data does.

The other four gases are one instrument (TROPOMI on Sentinel-5P) read through
one interface (Earth Engine) at one resolution, so they are the same program
with different constants. CO2 is not in Earth Engine at all, comes from four
different products with different resolutions and coverage windows, and its
signal at city scale is roughly 0.01% of its background — a hundredth of
methane's and a three-thousandth of NO2's.

So there is no `run_pipeline` returning one state dict, no raster with hotspot
boxes, and no single number. There are five analyses behind five tabs, each
of which can decline and explain instead. The usual outcome for a city is a
refusal, and that is the correct answer rather than a failure — `co2/NOTES.md`
has the measurements.

Two of the four CO2 products stopped years ago (assimilated XCO2 in February
2022, the emissions inventory in December 2023), so the page draws a coverage
timeline before it queries anything.

Backend and frontend stay per-gas on purpose — that is where the judgement
about a gas lives. What `shared/` holds is the machinery underneath them:
the map and the charts are drawn by shared code that a gas steers with a
small spec (`MapSpec`, `ChartSpec`), and the two Earth Engine passes that
are pure mechanics — daily means, hotspot segmentation — take the band and
the scale as arguments. Nothing in `shared/` knows a band name, a unit or a
threshold.

## Adding a gas

Four steps, in this order. Nothing outside the new folder and the registry
needs editing.

1. **Create the folder.** `mkdir no2/` and add an `__init__.py`.

2. **Write `no2/config.py` first.** Everything gas-specific goes here and
   nowhere else: the Earth Engine asset and band, the unit and any scale
   factor, the reduction scales, the level table, the palette, the vis
   fallback. `co/config.py` is the worked example — its comments explain not
   just what each constant is but why it has the value it has, which is the
   part worth copying.

3. **Write the pipeline and the views.** `co/backend.py` is the template:
   resolve the bbox, build a prepared collection, reduce the AOI, reduce the
   padded background box, trim to P10-P80, segment the hot tail, return one
   flat state dict. Lean on `shared/pipeline.py` for the daily series and the
   hotspot segmentation — both take your band and scale and hand the naming
   back to you.

   `mapview.py` and `chartview.py` are short: fill in a `MapSpec` and a
   `ChartSpec` saying what your numbers are called, what unit they are in and
   how many decimals they want, and write the two tooltip functions. The
   figures themselves come from `shared/`. Keep every threshold and unit
   coming from `config.py`.

4. **Register it.** Append a `Gas(...)` to `GASES` in `gas_registry.py` with
   `page="no2/frontend.py"`. The dashboard card and the sidebar entry appear
   on their own.

A gas can be declared before it is built: leave `page=None` and the dashboard
lists it greyed out while the router ignores it.

Those four steps assume the gas is a Sentinel-5P raster in Earth Engine. When
it is not — as with CO2 — step 2 still holds and steps 3 and 4 do not: write
whatever backend and views the data actually supports, and register it the
same way. The registry and the router care only that `page` names a script.

## Two things to know about the router

**`app.py` renders nothing before `page.run()`.** Streamlit only accepts
`set_page_config()` as the first message of a run, and every gas page sets
its own title and layout, so anything the router drew ahead of the page would
make that call raise. `st.navigation` is exempt — it sends a navigation
message rather than a UI delta. The shared sidebar is therefore drawn *after*
the page runs; no page uses the sidebar for its own controls, so the ordering
is invisible.

**Session state is namespaced per gas.** Each page keys its result
`<gas>_result` and its widgets `<gas>_*`, so results for different gases
coexist in one session and no page can read another's numbers by accident.
The current view lives in `<gas>_view` under the same convention; the
dashboard clears that key when its *Open ... agent* button is pressed, so
that button always lands on the agent's own landing page while the sidebar
returns you to whatever you were last looking at.

## Views within a gas

A gas page can offer more than one thing to do. Both built gases do:
`frontend.py` is a dispatcher that draws `home.py`'s cards, or the view whose
name sits in `<gas>_view`. Only `frontend.py` may call `set_page_config()` — Streamlit
accepts it as the first message of a run and nothing else — so the views draw
content only and know nothing about navigation.

Adding a view: write the module with a `render()`, add a `ModeCard` to
`home.py`, and map the card's `view` to the render function in `frontend.py`'s
`VIEWS`. A card with `enabled=False` draws greyed out with a dead button, the
same way the dashboard lists a gas that has no page behind it.

## Comparing two areas

`<gas>/compare.py` puts two areas of the same kind side by side over one date
range. Both gases have one, built the same way. Two things about it are
judgements rather than mechanics.

**Like compares to like.** Cities compare to cities and regions to regions.
A city AOI is a 0.3-degree box around a point; a region is a province. There
is no control that can mix them — the kind radio rebuilds both dropdowns.

**No background is computed anywhere on this page.** The compare view runs
`run_area_pipeline`, a second pipeline in `ch4/backend.py` that describes one
AOI purely on its own terms: no padded reference box, no enhancement, no
level. The two areas are each other's only reference, so a third one would
only muddy the comparison — and because nothing upstream computes a
background, nothing downstream can accidentally report one. It is also less
work: one fewer wide reduction, no context tiles, no per-day series.

That changes what a hotspot means here. A patch is boxed because it beats
**its own area's P80** — the hot fifth of that area's own pixels — so the
count answers "how broken up is this area's hot tail", which is a statement
about the area alone and therefore comparable across the two. Each patch
reports how far it sits above that cut (`above_cut_ppb`), not above any
background.

Each gas's two pipelines share their AOI machinery (`_spread_reducer`,
`_core_band`, `_vis_range`), so an area's own statistics are identical
whichever one measures it — verified for both gases: every shared key matches
exactly.

For CO specifically, the **clear-sky filter stays** on the compare page,
because it is not a background measure — it decides which retrievals are
admissible at all. But there is one control for both areas rather than one
each: comparing an area filtered at 500 m against one filtered at 2000 m
would compare two different measurements and read the difference as a finding
about the ground. What does go, along with the background, is CO's
regional-loading verdict, since that is read off the absolute background
column.

Under each card sit that area's own two charts: its pixel histogram, banded
on its own P10-P80, and its daily pixel availability. The histogram is there
because two areas can share a mean and share nothing else; the availability
chart because the two areas' numbers are only as comparable as the data
behind them, which for CO the clear-sky filter can skew badly between one
area and the other.

The map carries one raster at a time, chosen by a radio, because two
overlapping rasters cannot share a colour bar honestly. There is no
surrounding-area layer, and each gas's `mapview.py` gives the page its own
`COMPARE_SPEC` so no tooltip on it can speak of a background either.

## Gases

| Gas | Product | Band | Reported in | Classified on | Views |
|-----|---------|------|-------------|---------------|-------|
| CH4 | OFFL L3 CH4 | `CH4_column_volume_mixing_ratio_dry_air` | ppb, column mixing ratio | **ppb** above local background | single + compare |
| CO  | OFFL L3 CO  | `CO_column_number_density` | mmol/m², total column | **percent** above local background | single + compare |
| NO2 | OFFL L3 NO2 | `tropospheric_NO2_column_number_density` | µmol/m², tropospheric column | **percent** above local background | single |
| SO2 | OFFL L3 SO2 | `SO2_column_number_density` | µmol/m², column | **µmol/m²** above local background | single |

Three of the four arrive as a column in mol/m² and are scaled once, inside
Earth Engine, to whatever reads sanely in a metric: CO to mmol/m², NO2 and SO2
to µmol/m². Only CH4 is native — it is published as a dry-air mixing ratio in
ppb and needs no conversion. NO2 and SO2 are retrieved in the UV/visible, so
their footprint is 3.5 × 5.5 km and their `REDUCE_SCALE` is 5500 m; CH4 and CO
come from the shortwave infrared at 5.5 × 7 km and use 7000 m.

**Why the classification basis differs per gas.** It follows from how steady
each gas's background is, and getting it wrong would make an agent lie:

- **CH4** is long-lived and globally well mixed, so its background barely
  moves and a fixed ppb enhancement means the same thing everywhere.
- **CO** lasts weeks. Its background swings with latitude, season and
  whatever burned upwind — measured over the same Alberta box, June 2024 gave
  28.9 mmol/m² and a heavy August fire season 48.5 — so it is banded on a
  percentage, which travels.
- **NO2** lasts hours and never mixes to a global background at all. What it
  has is a regional one that moves with season and with how urban the
  surroundings are: measured in the same month of July 2026, the background
  around Athabasca was 10 µmol/m² and around Toronto 25. Percentage again.
- **SO2** is banded on an absolute figure, but for the opposite reason from
  methane's. Over clean air the retrieval scatters around zero and a good
  share of pixels come back *negative*, so a percentage of background would
  blow up wherever it landed near zero and flip sign wherever it landed
  below. There is deliberately no `_pct_above` in `so2/backend.py`.

**SO2 is the noisy one, and the agent says so.** Measured over July 2026, the
2nd percentile of the pixels inside these boxes ran to −78 µmol/m² over
Toronto, −106 over Athabasca and −100 over Alberta, while the area means sat
between 24 and 38 — the scatter on a single pixel is several times larger than
the difference between one area and another. Its level table therefore has a
**Within noise** band covering 0–50 µmol/m², drawn in grey rather than a
warning colour, and the page carries a banner above the headline metric
saying an enhancement inside that band is not a detection. TROPOMI sees SO2
reliably from strong sources — smelters, large power stations, sour-gas
plants, volcanoes — which run into the hundreds.

NO2 and SO2 have no compare view yet. Adding one is the `ch4/` split: move the
page body into `single_area.py`, add `home.py` and `compare.py`, and turn
`frontend.py` into the dispatcher. The shared `MapSpec`, `ChartSpec`,
`ModeCard` and `build_compare_map` took CO without a single change.

## Requirements

Earth Engine needs authenticating once:

```bash
earthengine authenticate
```

The Cloud project id is in `shared/earthengine.py` — the only copy; every
gas backend initialises through it.
