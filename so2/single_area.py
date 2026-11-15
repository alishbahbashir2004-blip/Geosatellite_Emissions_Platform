# so2/single_area.py
# One area, measured against its own surroundings: the SO2 agent proper. Same
# shape as the other gas pages — controls and metrics on the left, map and its
# distribution box plot on the right, charts below — with two additions that
# only SO2 needs:
#
#   * the enhancement is quoted in absolute µmol/m², not as a percentage,
#     because SO2's background scatters around zero (see config.py);
#   * a noise banner sits above the metrics, because on this product an
#     enhancement of a few tens of µmol/m² is not a detection and the page
#     should say so before the reader reads the number.
#
# Reached from so2/home.py by picking the first card. This module draws
# content only — the page title and the way back to the cards belong to
# so2/frontend.py, which is the thing the router actually runs.

import time

import streamlit as st
from streamlit_folium import st_folium

from shared.regions import REGIONS
from shared.cities import CITIES
from shared.globeview import render_globe, ZOOM_SECONDS
# `fmt` is bound to this gas's own precision rather than left on shared/ui's
# flat two decimals. The digit counts are the ones the gas already declares in
# its chartview SPEC — CH4 to 1dp because its interesting spread is tens of ppb
# against a ~1900 background, CO to 2dp because its whole range is small — and
# a metric and a chart tooltip disagreeing about the same number is confusing.
# No call site below passes `digits` positionally, so this reaches all of them.
from functools import partial as _partial
from shared.ui import fmt as _fmt
from shared.ui import fmt_range, level_delta, note
from so2.chartview import SPEC as _CHART_SPEC

fmt = _partial(_fmt, digits=_CHART_SPEC.digits)
from so2.backend import run_pipeline, resolve_bbox
from so2.config import (UNIT, DEFAULT_HOTSPOT_REGIONS, COVERAGE_START,
                        NOISE_NOTE)
from so2.mapview import build_result_map
from so2.chartview import (build_availability_chart, build_box_plot,
                           build_bg_histogram_chart, build_histogram_chart,
                           build_series_chart, level_legend_html)

MAP_HEIGHT = 430

# Session keys are namespaced, so the SO2 result and another gas's result can
# sit in the same session without either page reading the other's numbers.
RESULT_KEY = "so2_result"
LABEL_KEY = "so2_result_label"


def render():
    """Draw the whole single-area agent page."""
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0;'>Sulphur Dioxide "
        "Agent</h1>"
        "<p style='text-align:center;font-size:1.05rem;opacity:0.65;"
        "margin-top:0.4rem;'>"
        f"Sentinel-5P SO2 column ({UNIT}) from Google Earth Engine, "
        "measured against the surrounding region</p>",
        unsafe_allow_html=True,
    )

    controls_col, map_col = st.columns(2, gap="large")

    # The map column's slot is claimed before the controls are drawn. Streamlit
    # renders by column, not by code order, so the globe can be written here
    # from inside the controls block below and still land on the right-hand
    # side — which is what lets it spin while the query blocks.
    with map_col:
        st.subheader("Map")
        map_slot = st.empty()

    with controls_col:
        st.subheader("Location & date range")

        mode = st.radio("How do you want to specify location?",
                        ["Region name", "City name", "Coordinates"],
                        horizontal=True, key="so2_mode")

        region_name, city_name, N, S, W, E = None, None, None, None, None, None
        if mode == "Region name":
            region_name = st.selectbox("Region", sorted(REGIONS.keys()),
                                       key="so2_region")
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
            city_name = st.selectbox("City", options, key="so2_city")
        else:
            col1, col2 = st.columns(2)
            with col1:
                N = st.number_input("North", value=60.0, key="so2_n")
                S = st.number_input("South", value=49.0, key="so2_s")
            with col2:
                W = st.number_input("West", value=-120.0, key="so2_w")
                E = st.number_input("East", value=-110.0, key="so2_e")

        col1, col2 = st.columns(2)
        with col1:
            date_start = st.date_input("Start date", key="so2_start")
        with col2:
            date_end = st.date_input("End date", key="so2_end")
        st.caption(f"SO2 coverage starts {COVERAGE_START}.")

        # The box the user is currently pointing at, so the map can follow the
        # selection even before a query is run.
        selected_bbox, bbox_error = resolve_bbox(region_name, city_name, N, S, W, E)
        selected_label = region_name or city_name or "Selected area"

        focus = ((selected_bbox["N"] + selected_bbox["S"]) / 2,
                 (selected_bbox["E"] + selected_bbox["W"]) / 2) if selected_bbox else None

        if st.button("Get SO2 column", type="primary", key="so2_run"):
            # Spin the globe up first. Streamlit flushes each element as the
            # script produces it, so this reaches the browser and animates for
            # the length of the Earth Engine call rather than after it.
            anchor = time.time()
            with map_slot.container():
                render_globe(phase="launch", height=MAP_HEIGHT, anchor=anchor)
            with st.spinner("Querying Google Earth Engine..."):
                st.session_state[RESULT_KEY] = run_pipeline(
                    region_name=region_name, city_name=city_name,
                    N=N, S=S, W=W, E=E,
                    date_start=str(date_start), date_end=str(date_end),
                )
            st.session_state[LABEL_KEY] = selected_label

            if focus and not st.session_state[RESULT_KEY].get("error"):
                with map_slot.container():
                    render_globe(phase="zoom", focus=focus, height=MAP_HEIGHT,
                                 anchor=anchor, zoom_at=time.time())
                time.sleep(ZOOM_SECONDS)
            st.rerun()

        result = st.session_state.get(RESULT_KEY)

        # The stored result belongs to a different area than the one now selected —
        # show the numbers but let the map and charts follow the new selection.
        stale = bool(result and selected_bbox and result.get("bbox") != selected_bbox)
        result_label = st.session_state.get(LABEL_KEY, "Selected area")

        if result and result["error"]:
            st.error(result["error"])
        elif result:
            with st.container(border=True):
                st.caption(f"{result_label} — {result['pass_count']} satellite passes")

                # Read before the number, because it sets what the number is worth.
                st.markdown(note(NOISE_NOTE, "#78909c"), unsafe_allow_html=True)

                c1, c2, c3 = st.columns(3)
                c1.metric(f"Mean SO2 ({UNIT})", fmt(result.get("mean_so2")))
                c2.metric(f"Background ({UNIT})", fmt(result.get("background_so2")))
                # Percent is the headline, not the absolute difference: the levels
                # are assigned on it, and a raw column difference means nothing
                # without the background printed beside it.
                c3.metric("Above background",
                          fmt(result.get("enhancement_so2"), signed=True),
                          help="Area mean minus local background, in "
                               f"{UNIT}. Absolute rather than a percentage: SO2's "
                               "background scatters around zero, so a percentage "
                               "of it is not a quantity worth computing.")
                level_delta(c3, result.get("level"), result.get("enhancement_so2"))

                d1, d2, d3 = st.columns(3)
                d1.metric(f"Min ({UNIT})", fmt(result.get("min_so2")))
                d2.metric(f"Median ({UNIT})", fmt(result.get("median_so2")))
                d3.metric(f"Max ({UNIT})", fmt(result.get("max_so2")))

                e1, e2, _ = st.columns(3)
                e1.metric(f"P10-P80 ({UNIT})", fmt_range(result.get("p10_so2"),
                                                         result.get("p80_so2"),
                                                         digits=1))
                e2.metric(f"P10-P80 mean ({UNIT})", fmt(result.get("core_mean_so2")),
                          help="Mean of the AOI pixels that fall inside P10-P80, "
                               "so the low and high tails are excluded.")

                g1, g2, g3 = st.columns(3)
                g1.metric(f"Background P10-P80 ({UNIT})",
                          fmt_range(result.get("bg_p10_so2"),
                                    result.get("bg_p80_so2"), digits=1),
                          help="The surrounding region's own percentiles, measured "
                               "over the same period.")
                g2.metric(f"Background P10-P80 mean ({UNIT})",
                          fmt(result.get("bg_core_mean_so2")),
                          help="Mean of the surrounding region's pixels inside its "
                               "own P10-P80.")
                g3.metric("P10-P80 above bg",
                          fmt(result.get("core_enhancement_so2"), signed=True),
                          help="The two P10-P80 means differenced: "
                               "the AOI's bulk level against the background's, "
                               "with both tails off each side.")
                level_delta(g3, result.get("core_level"),
                            result.get("core_enhancement_so2"))

                # The area mean can look calm while a corner of the box is hot, so
                # the hot end gets the same above-background comparison.
                f1, f2, f3 = st.columns(3)
                f1.metric("Hotspot above bg",
                          fmt(result.get("hotspot_enhancement_so2"), signed=True),
                          help="Hottest fifth of the pixels (P80) minus local "
                               "background.")
                level_delta(f1, result.get("hotspot_level"),
                            result.get("hotspot_enhancement_so2"))
                f2.metric("Peak above bg",
                          fmt(result.get("peak_enhancement_so2"), signed=True),
                          help="Highest single pixel value minus local "
                               "background.")
                hotspots = result.get("hotspots")
                if hotspots:
                    hottest = hotspots[0]
                    found = result.get("hotspot_region_count") or len(hotspots)
                    shown_text = (f"{len(hotspots)}" if found <= len(hotspots)
                                  else f"{len(hotspots)} of {found}")
                    top = hottest.get("enhancement_so2")
                    f3.metric(
                        "Hotspot regions boxed", shown_text,
                        delta=(f"{top:+.1f} {UNIT} top patch" if top is not None
                               else None),
                        delta_color="inverse",
                        help=f"{found} contiguous patch(es) of above-P80 pixels "
                             f"were found inside the AOI; the {len(hotspots)} with "
                             "the highest mean are boxed on the map, numbered "
                             "hottest first.",
                    )

        if stale:
            st.info(f"Press *Get SO2 column* to load **{selected_label}**.")

    with map_slot.container():
        if result and not result["error"] and not stale:
            available = len(result.get("hotspots") or [])
            shown = min(DEFAULT_HOTSPOT_REGIONS, available)
            if available > 1:
                shown = st.slider(
                    "Hotspot boxes to draw", min_value=1, max_value=available,
                    value=min(DEFAULT_HOTSPOT_REGIONS, available),
                    key="so2_hotspot_count",
                    help=(f"Ranked by patch mean, hottest first. {available} "
                          "patches are available; the rest are weaker and "
                          "clutter the raster."),
                )
            st_folium(build_result_map(result, max_hotspots=shown),
                      use_container_width=True, height=MAP_HEIGHT,
                      returned_objects=[], key=f"so2_map_{shown}")
            if result.get("hotspot_error"):
                st.warning(result["hotspot_error"])
            elif not result.get("hotspots"):
                st.caption("No contiguous above-P80 patch large enough to box.")
        else:
            if bbox_error:
                st.warning(bbox_error)
            render_globe(phase="idle", height=MAP_HEIGHT)
            st.caption("Pick an area and a date range, then run a query to map "
                       "sulphur dioxide over it.")

    with map_col:
        if result and not result["error"] and not stale and result.get("box_stats"):
            st.markdown("**Box plot**")
            st.altair_chart(build_box_plot(result), use_container_width=True)
            st.caption(
                "P10–P80 spans the middle 70% of AOI pixel values; values below "
                "P10 and above P80 are the low/high tails."
            )

    st.divider()
    series_col, availability_col = st.columns(2, gap="large")

    with series_col:
        st.subheader("Daily mean SO2")
        if result and not result["error"] and result.get("series"):
            st.altair_chart(build_series_chart(result), use_container_width=True)
            st.markdown(level_legend_html(), unsafe_allow_html=True)
        elif result and not result["error"]:
            st.info("No daily values available for this area and date range.")
        else:
            st.info("Run a query to plot the SO2 column over time.")

    with availability_col:
        st.subheader("Daily data availability")
        if result and not result["error"] and result.get("availability"):
            st.altair_chart(build_availability_chart(result),
                            use_container_width=True)
            st.caption(
                "Pixels of the box sampled each day, split into valid retrievals "
                "and the ones cloud and quality masking removed. SO2 is retrieved "
                "in the UV, so a cloudy day leaves very little behind — and a thin "
                "valid band is one reason a scene reads as noise."
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
                "where a plume or a bad retrieval shows up."
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

    # --- How this reads next to the other gases ---------------------------------
    st.divider()
    st.subheader("Reading SO2 against the others")
    st.markdown(
        "SO2 comes from the same Sentinel-5P overpass as CH4, CO and NO2, so a "
        "given day's readings are co-located and same-time. It is the hardest of "
        "the four to see: the retrieval is noisy and only strong sources clear "
        "it. When it *does* clear, it is the most specific of the four."
    )
    st.markdown(
        "- **CO elevated and SO2 elevated** — sour gas or a refinery, not a "
        "sweet-gas flare. Sulphur in the feedstock is what puts SO2 in the "
        "plume.\n"
        "- **SO2 elevated and CO flat** — a smelter or a volcano rather than "
        "combustion.\n"
        "- **SO2 within noise** — the usual outcome away from a strong source, "
        "and not evidence that nothing is there. It means this instrument cannot "
        "tell from this scene."
    )
