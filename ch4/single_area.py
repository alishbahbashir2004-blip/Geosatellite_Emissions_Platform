# ch4/single_area.py
# One area vs. its surroundings: the methane agent proper. Controls/metrics
# left, map + box plot right, charts below. Page title/back-nav belong to frontend.py.

import time

import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium

from shared.regions import REGIONS
from shared.cities import CITIES
from shared.globeview import render_globe, ZOOM_SECONDS
# `fmt` is bound to this gas's own precision (from chartview.SPEC) rather than
# shared/ui's flat default, so metrics and chart tooltips agree on digits.
from functools import partial as _partial
from shared.ui import fmt as _fmt
from shared.ui import fmt_range, level_delta
from ch4.chartview import SPEC as _CHART_SPEC

fmt = _partial(_fmt, digits=_CHART_SPEC.digits)
from ch4.backend import run_pipeline, resolve_bbox
from ch4.config import UNIT, DEFAULT_HOTSPOT_REGIONS
from ch4.mapview import build_result_map
from ch4.chartview import (build_availability_chart, build_box_plot,
                           build_bg_histogram_chart, build_histogram_chart,
                           build_series_chart, level_legend_html)

# Global CH4 trend widget, served by methanelevels.org / climatelevels.org.
GLOBAL_CH4_WIDGET = (
    '<div id="ch4-widget-container"></div>'
    '<script type="text/javascript" src="https://www.climatelevels.org/'
    'graphs/js/ch4.php?theme=grid-light&pid=2degreesinstitute"></script>'
)

MAP_HEIGHT = 430

# Session keys are namespaced, so the methane result and another gas's result
# can sit in the same session without either page reading the other's numbers.
RESULT_KEY = "ch4_result"
LABEL_KEY = "ch4_result_label"


def render():
    """Draw the whole single-area agent page."""
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0;'>Methane Emission Agent</h1>"
        "<p style='text-align:center;font-size:1.05rem;opacity:0.65;margin-top:0.4rem;'>"
        f"Sentinel-5P CH4 Concentration ({UNIT}) from Google Earth Engine</p>",
        unsafe_allow_html=True,
    )

    controls_col, map_col = st.columns(2, gap="large")

    # Slot claimed before controls are drawn: Streamlit renders by column, not
    # code order, so the globe below still lands here and can spin.
    with map_col:
        st.subheader("Map")
        map_slot = st.empty()

    with controls_col:
        st.subheader("Location & date range")

        # --- Location input: region name OR city OR manual coordinates ---
        mode = st.radio("How do you want to specify location?",
                        ["Region name", "City name", "Coordinates"],
                        horizontal=True, key="ch4_mode")

        region_name, city_name, N, S, W, E = None, None, None, None, None, None
        if mode == "Region name":
            region_name = st.selectbox("Region", sorted(REGIONS.keys()),
                                       key="ch4_region")
        elif mode == "City name":
            # Support CITIES as either a dict (name->meta) or a list of city dicts
            if isinstance(CITIES, dict):
                options = sorted(CITIES.keys())
            elif isinstance(CITIES, list):
                options = sorted(
                    (c.get("name") if isinstance(c, dict) and c.get("name")
                     else str(c))
                    for c in CITIES
                )
            else:
                options = [str(CITIES)]
            city_name = st.selectbox("City", options, key="ch4_city")
        else:
            col1, col2 = st.columns(2)
            with col1:
                N = st.number_input("North", value=60.0, key="ch4_n")
                S = st.number_input("South", value=49.0, key="ch4_s")
            with col2:
                W = st.number_input("West", value=-120.0, key="ch4_w")
                E = st.number_input("East", value=-110.0, key="ch4_e")

        # --- Date range input ---
        col1, col2 = st.columns(2)
        with col1:
            date_start = st.date_input("Start date", key="ch4_start")
        with col2:
            date_end = st.date_input("End date", key="ch4_end")

        # The box the user is currently pointing at, so the map can follow the
        # selection even before a query is run.
        selected_bbox, bbox_error = resolve_bbox(region_name, city_name, N, S, W, E)
        selected_label = region_name or city_name or "Selected area"

        focus = ((selected_bbox["N"] + selected_bbox["S"]) / 2,
                 (selected_bbox["E"] + selected_bbox["W"]) / 2) if selected_bbox else None

        if st.button("Get CH4 concentration", type="primary", key="ch4_run"):
            # Streamlit flushes each element as produced, so this animates
            # during the Earth Engine call rather than after it.
            anchor = time.time()
            with map_slot.container():
                render_globe(phase="launch", height=MAP_HEIGHT, anchor=anchor)
            with st.spinner("Querying Google Earth Engine..."):
                st.session_state[RESULT_KEY] = run_pipeline(
                    region_name=region_name, city_name=city_name,
                    N=N, S=S, W=W, E=E,
                    date_start=str(date_start), date_end=str(date_end),
                )
            # Stashed so panning/zooming the map (which reruns the script)
            # doesn't re-query Earth Engine.
            st.session_state[LABEL_KEY] = selected_label

            # Same `anchor` for both phases so the push-in picks up the spin
            # mid-turn. Skipped if the query failed.
            if focus and not st.session_state[RESULT_KEY].get("error"):
                with map_slot.container():
                    render_globe(phase="zoom", focus=focus, height=MAP_HEIGHT,
                                 anchor=anchor, zoom_at=time.time())
                time.sleep(ZOOM_SECONDS)
            st.rerun()

        result = st.session_state.get(RESULT_KEY)

        # True if the stored result is for a different area than now selected.
        stale = bool(result and selected_bbox and result.get("bbox") != selected_bbox)
        result_label = st.session_state.get(LABEL_KEY, "Selected area")

        if result and result["error"]:
            st.error(result["error"])
        elif result:
            with st.container(border=True):
                st.caption(f"{result_label} — {result['pass_count']} satellite passes")
                c1, c2, c3 = st.columns(3)
                c1.metric(f"Mean CH4 ({UNIT})", fmt(result.get("mean_ch4_ppb")))
                if result.get("background_ch4_ppb") is not None:
                    c2.metric(f"Background ({UNIT})",
                              fmt(result.get("background_ch4_ppb")))
                if result.get("enhancement_ppb") is not None:
                    c3.metric("Above background",
                              fmt(result.get("enhancement_ppb"), signed=True))
                    level_delta(c3, result.get("level"),
                                result["enhancement_ppb"])
                else:
                    c3.metric("Emission level", result.get("level", "Unknown"))

                d1, d2, d3 = st.columns(3)
                d1.metric(f"Min ({UNIT})", fmt(result.get("min_ch4_ppb")))
                d2.metric(f"Median ({UNIT})", fmt(result.get("median_ch4_ppb")))
                d3.metric(f"Max ({UNIT})", fmt(result.get("max_ch4_ppb")))

                # Both tails trimmed before differencing, so a cloud-thinned
                # pass or a single plume doesn't move the number.
                e1, e2, _ = st.columns(3)
                e1.metric(f"P10-P80 ({UNIT})", fmt_range(result.get("p10_ch4_ppb"),
                                                         result.get("p80_ch4_ppb")))
                e2.metric(f"P10-P80 mean ({UNIT})",
                          fmt(result.get("core_mean_ch4_ppb")),
                          help="Mean of the AOI pixels that fall inside P10-P80, "
                               "so the low and high tails are excluded.")

                g1, g2, g3 = st.columns(3)
                g1.metric(f"Background P10-P80 ({UNIT})",
                          fmt_range(result.get("bg_p10_ch4_ppb"),
                                    result.get("bg_p80_ch4_ppb")),
                          help="The surrounding region's own percentiles, measured "
                               "over the same period.")
                g2.metric(f"Background P10-P80 mean ({UNIT})",
                          fmt(result.get("bg_core_mean_ch4_ppb")),
                          help="Mean of the surrounding region's pixels inside its "
                               "own P10-P80.")
                if result.get("core_enhancement_ppb") is not None:
                    g3.metric("P10-P80 above bg",
                              fmt(result.get("core_enhancement_ppb"), signed=True),
                              help="The two P10-P80 means differenced: the AOI's "
                                   "bulk level against the background's, with both "
                                   "tails off each side.")
                    level_delta(g3, result.get("core_level"),
                                result.get("core_enhancement_ppb"))

                # Hot end gets the same above-background comparison, since a
                # small plume barely moves the area mean.
                f1, f2, f3 = st.columns(3)
                f1.metric(
                    "Hotspot above bg", fmt(result.get("hotspot_enhancement_ppb"),
                                            signed=True),
                    help="Hottest fifth of the pixels (P80) minus local background.",
                )
                level_delta(f1, result.get("hotspot_level"),
                            result.get("hotspot_enhancement_ppb"))
                f2.metric(
                    "Peak value above bg", fmt(result.get("peak_enhancement_ppb"),
                                               signed=True),
                    help="Highest single pixel value minus local background.",
                )
                hotspots = result.get("hotspots")
                if hotspots:
                    hottest = hotspots[0]
                    found = result.get("hotspot_region_count") or len(hotspots)
                    # Show what the map shows, not just the raw total found.
                    shown_text = (f"{len(hotspots)}" if found <= len(hotspots)
                                  else f"{len(hotspots)} of {found}")
                    f3.metric(
                        "Hotspot regions boxed", shown_text,
                        delta=fmt(hottest.get("enhancement_ppb"), digits=1,
                                  signed=True) + f" {UNIT} top patch"
                        if hottest.get("enhancement_ppb") is not None else None,
                        delta_color="inverse",
                        help=f"{found} contiguous patch(es) of above-P80 pixels "
                             f"were found inside the AOI; the {len(hotspots)} with "
                             "the highest mean are boxed on the map, numbered "
                             "hottest first. A large AOI breaks its hot tail into "
                             "many patches, so only the strongest are drawn.",
                    )

        if stale:
            st.info(f"Press *Get CH4 concentration* to load **{selected_label}**.")

    # Filling the slot claimed above: current result gets the real map,
    # anything else (nothing queried yet, or stale) falls back to the globe.
    with map_slot.container():
        if result and not result["error"] and not stale:
            # Backend returns more patches than the map draws by default, so
            # moving this slider only rebuilds the map — no re-query.
            available = len(result.get("hotspots") or [])
            shown = min(DEFAULT_HOTSPOT_REGIONS, available)
            if available > 1:
                shown = st.slider(
                    "Hotspot boxes to draw", min_value=1, max_value=available,
                    value=min(DEFAULT_HOTSPOT_REGIONS, available),
                    key="ch4_hotspot_count",
                    help=(f"Ranked by patch mean, hottest first. {available} "
                          "patches are available; the rest are weaker and "
                          "clutter the raster."),
                )
            st_folium(build_result_map(result, max_hotspots=shown),
                      use_container_width=True, height=MAP_HEIGHT,
                      returned_objects=[], key=f"ch4_map_{shown}")
            # A missing overlay should never be mistaken for a clean AOI.
            if result.get("hotspot_error"):
                st.warning(result["hotspot_error"])
            elif not result.get("hotspots"):
                st.caption("No contiguous above-P80 patch large enough to box.")
        else:
            if bbox_error:
                st.warning(bbox_error)
            render_globe(phase="idle", height=MAP_HEIGHT)
            st.caption("Pick an area and a date range, then run a query to map "
                       "methane over it.")

    with map_col:
        # Same pixels the map shows, summarised.
        if result and not result["error"] and not stale and result.get("box_stats"):
            st.markdown("**Box plot**")
            st.altair_chart(build_box_plot(result), use_container_width=True)
            st.caption(
                "P10–P80 spans the middle 70% of AOI pixel values; values below "
                "P10 and above P80 are the low/high tails."
            )

    # --- Charts, full width below the map. Add further charts as new rows here.
    st.divider()
    series_col, availability_col = st.columns(2, gap="large")

    with series_col:
        st.subheader("Daily mean CH4")
        if result and not result["error"] and result.get("series"):
            st.altair_chart(build_series_chart(result), use_container_width=True)
            st.markdown(level_legend_html(), unsafe_allow_html=True)
        elif result and not result["error"]:
            st.info("No daily values available for this area and date range.")
        else:
            st.info("Run a query to plot methane concentration over time.")

    with availability_col:
        st.subheader("Daily data availability")
        if result and not result["error"] and result.get("availability"):
            st.altair_chart(build_availability_chart(result), use_container_width=True)
            st.caption(
                "Pixels of the box sampled each day, split into valid retrievals "
                "and the ones cloud and quality masking removed. Days with a thin "
                "valid band carry a mean built from very few pixels."
            )
        elif result and not result["error"]:
            st.info("No per-day pixel counts available for this area and date range.")
        else:
            st.info("Run a query to see how much of the box survives the mask.")

    histogram_col, bg_histogram_col = st.columns(2, gap="large")

    with histogram_col:
        st.subheader("AOI P10-P80 histogram")
        if result and not result["error"] and result.get("histogram"):
            st.altair_chart(build_histogram_chart(result), use_container_width=True)
            st.caption(
                "Every pixel of the selected area, split on its own P10-P80. The "
                "middle band holds 70% of them by construction; the tails are "
                "where a leak or a bad retrieval shows up."
            )
        else:
            st.info("Run a query to see the spread of pixel values.")

    with bg_histogram_col:
        st.subheader("Background P10-P80 histogram")
        if result and not result["error"] and result.get("bg_histogram"):
            st.altair_chart(build_bg_histogram_chart(result),
                            use_container_width=True)
            st.caption(
                "The surrounding region over the same period, banded on its own "
                "P10-P80 — the same chart as the left, over different pixels. Its "
                "middle band is the level the selected area is measured against."
            )
        elif result and not result["error"]:
            st.info("No background distribution available for this area.")
        else:
            st.info("Run a query to see the background distribution.")

    # --- Global context, full width: not tied to the selected area or dates. ---
    st.divider()
    st.subheader("Global methane trend")
    components.html(GLOBAL_CH4_WIDGET, height=460)
