# co2/frontend.py
# The CO2 page: four tabs, each a different product/claim (see each tab's
# badge), each free to decline and say why instead of printing a bad number.

import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Carbon Dioxide Agent",
                   page_icon=":material/co2:", layout="wide")

from shared.regions import REGIONS
from shared.cities import CITIES
from co2 import backend, chartview, mapview
from co2.config import (SOURCES, WHY_TOO_SMALL, NO2_COVERAGE_START,
                        EMISSION_RATIOS)

MAP_HEIGHT = 430
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

KIND_BADGE = {
    "observation": ("#2e7d32", "MEASURED",
                    "Real soundings. A satellite saw this."),
    "assimilation": ("#f57c00", "ASSIMILATED",
                     "A transport model, pulled towards real soundings every "
                     "six hours. Gap-free because the model fills the gaps."),
    "inventory": ("#6a1b9a", "MODELLED",
                  "A bottom-up emissions estimate spread over a grid. "
                  "Nothing here was measured in the atmosphere."),
    "inferred": ("#0277bd", "INFERRED",
                 "Calculated from a different gas that was measured. No "
                 "satellite saw this CO2."),
}


# ---------------------------------------------------------------------------
# Small presentation helpers
# ---------------------------------------------------------------------------

def badge(kind):
    colour, text, explanation = KIND_BADGE[kind]
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:0.6rem;"
        f"margin:0.2rem 0 0.8rem 0;'>"
        f"<span style='background:{colour};color:#fff;font-size:0.68rem;"
        f"font-weight:700;letter-spacing:0.08em;padding:0.18rem 0.5rem;"
        f"border-radius:3px;'>{text}</span>"
        f"<span style='opacity:0.7;font-size:0.86rem;'>{explanation}</span>"
        f"</div>", unsafe_allow_html=True)


def explain(html, tone="info"):
    tint = {"info": "rgba(128,128,128,0.10)",
            "warn": "rgba(245,124,0,0.12)",
            "stop": "rgba(198,40,40,0.10)"}[tone]
    edge = {"info": "#78909c", "warn": "#f57c00", "stop": "#c62828"}[tone]
    st.markdown(
        f"<div style='background:{tint};border-left:3px solid {edge};"
        f"padding:0.7rem 0.9rem;border-radius:0 4px 4px 0;margin:0.5rem 0;"
        f"font-size:0.9rem;line-height:1.5;'>{html}</div>",
        unsafe_allow_html=True)


def unavailable(result, extra_html=None):
    """The standard 'no reading, and here is why' block.

    Every tab funnels its refusals through here so the reason always looks
    like an answer rather than like an error.
    """
    st.markdown(f"#### {result['reason']}")
    explain(result["detail"], tone="stop")
    if extra_html:
        explain(extra_html, tone="info")
    check = result.get("adequacy")
    if check:
        c1, c2, c3 = st.columns(3)
        c1.metric("Your area spans", f"{check['cells']:.1f} cells")
        c2.metric("One cell is",
                  f"{check['cell_km'][0]:.0f} × {check['cell_km'][1]:.0f} km")
        c3.metric("Needed for a reading", "4 cells (2×2)")


def run_button(label, key):
    return st.button(label, type="primary", key=key)


# ---------------------------------------------------------------------------
# Header and shared controls
# ---------------------------------------------------------------------------

st.markdown(
    "<h1 style='text-align:center;margin-bottom:0;'>Carbon Dioxide Agent</h1>"
    "<p style='text-align:center;font-size:1.05rem;opacity:0.65;"
    "margin-top:0.4rem;'>Four CO2 products plus one NO2-based inference, each "
    "a different kind of claim — the badge on each tab says which.</p>",
    unsafe_allow_html=True)

with st.container(border=True):
    left, right = st.columns([2, 3], gap="large")

    with left:
        mode = st.radio("Location", ["Region name", "City name", "Coordinates"],
                        horizontal=True, key="co2_mode")
        region_name = city_name = None
        N = S = W = E = None
        if mode == "Region name":
            region_name = st.selectbox("Region", sorted(REGIONS.keys()),
                                       key="co2_region")
        elif mode == "City name":
            options = (sorted(CITIES.keys()) if isinstance(CITIES, dict)
                       else sorted(c.get("name", str(c)) if isinstance(c, dict)
                                   else str(c) for c in CITIES))
            city_name = st.selectbox("City", options, key="co2_city")
        else:
            c1, c2 = st.columns(2)
            with c1:
                N = st.number_input("North", value=60.0, key="co2_n")
                S = st.number_input("South", value=49.0, key="co2_s")
            with c2:
                W = st.number_input("West", value=-120.0, key="co2_w")
                E = st.number_input("East", value=-110.0, key="co2_e")

        d1, d2 = st.columns(2)
        with d1:
            date_start = st.date_input("Start date", key="co2_start")
        with d2:
            date_end = st.date_input("End date", key="co2_end")

    bbox, bbox_error = backend.resolve_bbox(region_name, city_name, N, S, W, E)
    label = region_name or city_name or "Selected area"
    start_text, end_text = str(date_start), str(date_end)

    with right:
        st.markdown("**What CO2 data exists, and when**")
        st.altair_chart(
            chartview.build_coverage_chart(
                backend.coverage_timeline(start_text, end_text),
                start_text, end_text),
            use_container_width=True)

if bbox_error:
    st.error(bbox_error)
    st.stop()

timeline = backend.coverage_timeline(start_text, end_text)
stale = [row for row in timeline if not row["covers_request"]]
if stale:
    names = ", ".join(row["label"] for row in stale)
    st.caption(f"Your date range falls outside {len(stale)} source(s): "
              f"{names}. Those tabs will use their nearest data instead, or "
              "decline and say why.")

tab_trend, tab_inventory, tab_snapshot, tab_inferred = st.tabs([
    "Trend & seasonal cycle", "Emissions inventory",
    "Targeted snapshots", "CO2 inferred from NO2"])


# ---------------------------------------------------------------------------
# Tab 1 — trend and seasonal cycle
# ---------------------------------------------------------------------------

with tab_trend:
    badge(SOURCES["xco2_grid"]["kind"])
    st.caption(SOURCES["xco2_grid"]["what_it_is"], unsafe_allow_html=True)
    st.caption("Reads this area's entire record, not just your selected "
              "dates — a trend needs years of data. Your window is shaded "
              "on the chart.")

    if run_button("Read the CO2 record for this area", "co2_run_trend"):
        with st.spinner("Reading seven years of XCO2 over this area…"):
            st.session_state["co2_trend"] = backend.run_trend(bbox, label)
        st.session_state["co2_trend_bbox"] = bbox

    result = st.session_state.get("co2_trend")
    if result and st.session_state.get("co2_trend_bbox") != bbox:
        st.info(f"Press the button to load **{label}**.")
    elif result and not result["available"]:
        unavailable(result, WHY_TOO_SMALL
                    if "smaller" in result["reason"] else None)
        if result.get("adequacy"):
            st.markdown("**What that looks like on a map**")
            st_folium(mapview.build_grid_map(bbox, "xco2_grid",
                                             result["adequacy"], label=label),
                      use_container_width=True, height=MAP_HEIGHT,
                      returned_objects=[], key="co2_grid_map_trend")
            st.caption("Each white rectangle is one grid cell of the product. "
                       "The blue box is your area.")
    elif result:
        a, b, c, d = st.columns(4)
        a.metric("Long-term rise",
                 f"{result['slope_ppm_per_year']:+.2f} ppm/yr")
        if result["seasonal_amplitude"] is not None:
            b.metric("Seasonal swing", f"{result['seasonal_amplitude']:.2f} ppm",
                     help="Peak-to-trough of the yearly cycle, averaged over "
                          "every full year in the record.")
            c.metric("High / low month",
                     f"{MONTHS[result['seasonal_max_month'] - 1][:3]} / "
                     f"{MONTHS[result['seasonal_min_month'] - 1][:3]}")
        d.metric("Left-over scatter", f"±{result['remainder_std']:.2f} ppm",
                 help="Standard deviation of what remains once the rise and "
                      "the yearly cycle are removed. Anything smaller than "
                      "this cannot be distinguished from noise.")
        st.caption(f"{result['n']} usable days between {result['first']} and "
                   f"{result['last']}; the area spans "
                   f"{result['adequacy']['cells']:.0f} grid cells.")

        st.altair_chart(
            chartview.build_record_chart(result, start_text, end_text),
            use_container_width=True)
        st.caption("The rise is global — it reflects humanity's total "
                   "emissions, not this area specifically.")

        seasonal = chartview.build_seasonal_chart(result)
        if seasonal is not None:
            st.markdown("##### The yearly cycle, on its own")
            st.altair_chart(seasonal, use_container_width=True)
            st.caption(f"Measured swing over {result['label']}: "
                      f"{result['seasonal_amplitude']:.2f} ppm, peaking in "
                      f"{MONTHS[result['seasonal_max_month'] - 1]} and "
                      f"bottoming in "
                      f"{MONTHS[result['seasonal_min_month'] - 1]}.")
        else:
            st.caption("Not enough full years in this area's record to "
                      "separate a seasonal cycle from the rise.")

        st.markdown("##### What is left once both are removed")
        st.altair_chart(chartview.build_remainder_chart(result),
                        use_container_width=True)
        st.caption("A single city or oil field moves CO2 by hundredths of a "
                   "ppm — far smaller than the rise and the seasonal swing "
                   "just removed, which is why both had to go first.")


# ---------------------------------------------------------------------------
# Tab 2 — the emissions inventory
# ---------------------------------------------------------------------------

with tab_inventory:
    badge(SOURCES["odiac"]["kind"])
    st.caption(SOURCES["odiac"]["what_it_is"], unsafe_allow_html=True)
    st.caption("The only CO2 product here fine enough to separate a city "
              "from the countryside (1 km, monthly) — a modelled estimate of "
              "where CO2 is emitted, not a measurement of it.")

    if run_button("Read the emissions inventory", "co2_run_inventory"):
        with st.spinner("Reading ODIAC…"):
            st.session_state["co2_inventory"] = backend.run_inventory(
                bbox, start_text, end_text, label)
        st.session_state["co2_inventory_bbox"] = bbox

    result = st.session_state.get("co2_inventory")
    if result and st.session_state.get("co2_inventory_bbox") != bbox:
        st.info(f"Press the button to load **{label}**.")
    elif result and not result["available"]:
        unavailable(result)
    elif result:
        gap = result.get("gap")
        if gap:
            explain(
                f"Your window was trimmed to what the inventory has: "
                f"<b>{result['window'][0]} to {result['window'][1]}</b>. "
                f"ODIAC covers {gap['source_range'][0]} to "
                f"{gap['source_range'][1]}.", tone="warn")

        latest = result["latest"]
        a, b, c, d = st.columns(4)
        a.metric(f"Emissions, {latest['date'][:7]} × 12",
                 f"{latest['total_mtco2_per_year']:,.1f} Mt CO2/yr",
                 help="Every emitting cell in the area for this one month, "
                      "multiplied by twelve — not a calendar-year total. "
                      "ODIAC's months differ by a quarter either way, so use "
                      "the chart below rather than one bar. December 2023 "
                      "over the whole of Alberta gives 168 Mt CO2/yr this "
                      "way, against a real provincial fossil-fuel figure "
                      "near 170, which is the check worth doing on any "
                      "number like this one.")
        b.metric("Biggest single cell",
                 f"{latest['peak_mtco2_per_year_cell']:,.2f} Mt CO2/yr",
                 help="The most intense 1 km cell in the area, annualised — "
                      "a power station, a refinery or an upgrader complex.")
        c.metric("Intensity",
                 f"{latest['mean_tco2_per_km2_month']:,.0f} t/km²/mo",
                 help="Tonnes of CO2 per square kilometre per month, over "
                      "emitting land only — not spread across the whole box.")
        d.metric("Emitting land",
                 f"{latest['emitting_share'] * 100:.0f}%",
                 help="Share of the area with any fossil-fuel activity at "
                      "all. ODIAC leaves the rest empty rather than zero, so "
                      "the intensity above is a mean over this part only.")
        st.caption(f"Latest month shown: {latest['date'][:7]}. Area ≈ "
                   f"{latest['area_km2']:,.0f} km², of which "
                   f"{latest['emitting_km2']:,.0f} km² emits anything.")

        with st.expander("Show the raw numbers and the arithmetic"):
            st.markdown(
                f"**What the GHG Center returned for {latest['date'][:7]}** — "
                f"four numbers, in tonnes of *carbon* per grid cell per "
                f"month. Everything above is arithmetic on these.")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("mean per cell",
                      f"{latest['raw_mean_tc_per_cell']:,.4f} tC")
            r2.metric("cells with a value",
                      f"{latest['raw_cell_count']:,.0f}")
            r3.metric("max cell",
                      f"{latest['raw_max_tc_per_cell']:,.1f} tC")
            r4.metric("of cells in box",
                      f"{latest['raw_valid_percent']:.2f}%")
            st.code(
                f"carbon -> CO2 = 44/12 = 3.6667\n\n"
                f"1  emissions  = mean x cells x 44/12 x 12 / 1e6\n"
                f"              = {latest['raw_mean_tc_per_cell']:,.4f}"
                f" x {latest['raw_cell_count']:,.0f} x 3.6667 x 12 / 1e6\n"
                f"              = {latest['total_mtco2_per_year']:,.2f}"
                f" Mt CO2/yr\n\n"
                f"2  biggest    = max x 44/12 x 12 / 1e6\n"
                f"              = {latest['raw_max_tc_per_cell']:,.1f}"
                f" x 3.6667 x 12 / 1e6\n"
                f"              = {latest['peak_mtco2_per_year_cell']:,.2f}"
                f" Mt CO2/yr\n\n"
                f"3  intensity  = mean x 44/12 / cell_km2\n"
                f"              = {latest['raw_mean_tc_per_cell']:,.4f}"
                f" x 3.6667 / {latest['cell_km2']:.4f}\n"
                f"              = {latest['mean_tco2_per_km2_month']:,.0f}"
                f" t CO2/km²/month\n\n"
                f"4  emitting   = cells x cell_km2 / box area\n"
                f"              = {latest['raw_cell_count']:,.0f}"
                f" x {latest['cell_km2']:.4f} / {latest['area_km2']:,.0f}\n"
                f"              = {latest['emitting_share'] * 100:.0f}%"
                f"  ({latest['emitting_km2']:,.0f} km²)",
                language="text")
            st.caption(
                "ODIAC leaves land with no fossil-fuel activity empty rather "
                "than zero, so 'mean per cell' is a mean over emitting cells "
                "only — which is why line 1 multiplies by the cell count and "
                "not by the box area.")

        st.altair_chart(chartview.build_inventory_chart(result),
                        use_container_width=True)
        st_folium(mapview.build_inventory_map(result),
                  use_container_width=True, height=MAP_HEIGHT,
                  returned_objects=[], key="co2_inventory_map")
        st.caption("An allocation of a national total by night-lights and "
                  "plant locations — where emissions should be, not a plume "
                  "anyone photographed.")


# ---------------------------------------------------------------------------
# Tab 3 — targeted snapshots
# ---------------------------------------------------------------------------

with tab_snapshot:
    badge(SOURCES["sam"]["kind"])
    st.caption(SOURCES["sam"]["what_it_is"], unsafe_allow_html=True)

    if run_button("Find targeted snapshots over this area",
                  "co2_run_snapshot"):
        with st.spinner("Searching for pointed overpasses…"):
            st.session_state["co2_snapshot"] = backend.run_snapshots(
                bbox, start_text, end_text, label)
        st.session_state["co2_snapshot_bbox"] = bbox

    result = st.session_state.get("co2_snapshot")
    if result and st.session_state.get("co2_snapshot_bbox") != bbox:
        st.info(f"Press the button to load **{label}**.")
    elif result and not result["available"]:
        unavailable(result)
    elif result:
        if result["used_out_of_window"]:
            st.caption(
                f"No snapshot fell inside your dates "
                f"({result['requested'][0]} to {result['requested'][1]}), so "
                f"the most recent one ever taken is shown instead: "
                f"{result['chosen']['date']}. These overpasses are "
                "opportunistic, not scheduled.")

        stats = result["stats"]
        a, b, c, d = st.columns(4)
        a.metric("Area actually measured",
                 f"{result['covered_km2']:,.0f} km²",
                 help=f"These snapshots are published on a very fine grid — "
                      f"800 × 800 cells across the footprint, about 80 × 140 m "
                      f"each — which is finer than the satellite's real ~2 km "
                      f"footprint, so one reading paints several cells. "
                      f"{result['filled_cells']:,.0f} cells carry data, "
                      f"covering this much ground out of a "
                      f"{result['footprint_km2']:,.0f} km² footprint. Cloud "
                      f"and aerosol screening account for most of the rest.")
        b.metric("Mean XCO2", f"{stats['mean']:.2f} ppm")
        c.metric("Spread across the site", f"{result['spread']:.2f} ppm")
        d.metric("Snapshots ever here", f"{len(result['all_items'])}")
        st.caption(f"Showing {result['chosen']['date']}. "
                   f"{len(result['in_window'])} of "
                   f"{len(result['all_items'])} fall inside your dates.")

        st_folium(mapview.build_snapshot_map(result),
                  use_container_width=True, height=MAP_HEIGHT,
                  returned_objects=[], key="co2_snapshot_map")
        st.caption("Orange = what the satellite covered on this pass; blue = "
                  "your selection. Anything outside the orange has no data "
                  "on this date.")

        histogram = chartview.build_snapshot_histogram(result)
        if histogram is not None:
            st.markdown("##### Distribution of this snapshot's soundings")
            st.altair_chart(histogram, use_container_width=True)

        strip = chartview.build_snapshot_timeline(result)
        if strip is not None:
            st.markdown("##### Every snapshot ever taken over this area")
            st.altair_chart(strip, use_container_width=True)
            st.caption("Each tick is one pointed overpass. The gaps are the "
                       "point: this is not a time series.")


# ---------------------------------------------------------------------------
# Tab 4 — inferred from NO2
# ---------------------------------------------------------------------------

with tab_inferred:
    badge("inferred")
    st.caption("The only analysis here that works at city scale and at "
              "this year's dates: combustion emits CO2 and NOx together, so "
              "the visible NO2 is scaled by their emission ratio.")

    if run_button("Infer combustion CO2 from NO2", "co2_run_inferred"):
        with st.spinner("Querying Earth Engine for NO2…"):
            st.session_state["co2_inferred"] = backend.run_inferred(
                bbox, start_text, end_text, label)
        st.session_state["co2_inferred_bbox"] = bbox

    result = st.session_state.get("co2_inferred")
    if result and st.session_state.get("co2_inferred_bbox") != bbox:
        st.info(f"Press the button to load **{label}**.")
    elif result and not result["available"]:
        unavailable(result)
    elif result:
        if result["clamped"]:
            st.caption(f"Start date moved to {result['window'][0]} — "
                      f"Sentinel-5P NO2 begins {NO2_COVERAGE_START}.")

        if result["no_plume"]:
            st.markdown("#### No combustion plume to infer from")
            explain(
                f"This area's NO2 is <b>{result['no2_delta']:+.1f} µmol/m²</b> "
                "against its surroundings — at or below the background, so "
                "there is no combustion signal to scale. Expected for rural "
                "areas and for a region whose surroundings are just as "
                "industrial as it is.", tone="stop")
        else:
            inferred = result["inferred"]
            a, b, c = st.columns(3)
            a.metric("NO2 above surroundings",
                     f"{result['no2_delta']:+.1f} µmol/m²",
                     delta=f"{result['no2_pct']:+.1f}% of background")
            b.metric("Implied combustion CO2",
                     f"{inferred['central']:.3f} ppm",
                     help=f"Using the central CO2:NOx ratio of "
                          f"{EMISSION_RATIOS['central']:.0f}:1.")
            c.metric("Plausible range",
                     f"{inferred['low']:.3f} – {inferred['high']:.3f} ppm")

            st.altair_chart(chartview.build_inferred_chart(result),
                            use_container_width=True)
            st.caption("Inferred, not measured — the CO2:NOx ratio is "
                      "uncertain by a factor of several, which is why a "
                      "range is shown rather than one figure.")

            st.markdown("##### The two boxes this came from")
            st_folium(mapview.build_inferred_map(result),
                      use_container_width=True, height=MAP_HEIGHT,
                      returned_objects=[], key="co2_inferred_map")
            st.caption(f"NO2 measured over {result['window'][0]} to "
                       f"{result['window'][1]} from "
                       f"{result.get('no2_pixels') or 0:,.0f} pixels.")
