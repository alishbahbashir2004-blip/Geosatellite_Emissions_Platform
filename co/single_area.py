# co/single_area.py
# One area vs. its surroundings: the CO agent proper. Same shape as the
# methane page, plus a clear-sky control and regional-loading banner (CO-only).

import time

import streamlit as st
from streamlit_folium import st_folium

from shared.regions import REGIONS
from shared.cities import CITIES
from shared.globeview import render_globe, ZOOM_SECONDS
# `fmt` is bound to this gas's own precision (from chartview.SPEC) rather than
# shared/ui's flat default, so metrics and chart tooltips agree on digits.
from functools import partial as _partial
from shared.ui import fmt as _fmt
from shared.ui import fmt_range, fmt_pct, level_delta, note
from co.chartview import SPEC as _CHART_SPEC

fmt = _partial(_fmt, digits=_CHART_SPEC.digits)
from co.backend import run_pipeline, resolve_bbox
from co.config import (UNIT, DEFAULT_HOTSPOT_REGIONS, CLEAR_SKY_DEFAULT,
                       DEFAULT_CLOUD_CEILING_M, CLOUD_CEILING_CHOICES,
                       COVERAGE_START)
from co.mapview import build_result_map
from co.chartview import (build_availability_chart, build_box_plot,
                          build_bg_histogram_chart, build_histogram_chart,
                          build_series_chart, level_legend_html,
                          loading_legend_html)

MAP_HEIGHT = 430

# Session keys are namespaced, so the CO result and another gas's result can
# sit in the same session without either page reading the other's numbers.
RESULT_KEY = "co_result"
LABEL_KEY = "co_result_label"


def render():
    """Draw the whole single-area CO agent page."""
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0;'>"
        "Carbon Monoxide Agent</h1>"
        "<p style='text-align:center;font-size:1.05rem;opacity:0.65;"
        "margin-top:0.4rem;'>"
        f"Sentinel-5P CO total column ({UNIT}) from Google Earth Engine, measured "
        "against the surrounding region</p>",
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
                        horizontal=True, key="co_mode")

        region_name, city_name, N, S, W, E = None, None, None, None, None, None
        if mode == "Region name":
            region_name = st.selectbox("Region", sorted(REGIONS.keys()),
                                       key="co_region")
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
            city_name = st.selectbox("City", options, key="co_city")
        else:
            col1, col2 = st.columns(2)
            with col1:
                N = st.number_input("North", value=60.0, key="co_n")
                S = st.number_input("South", value=49.0, key="co_s")
            with col2:
                W = st.number_input("West", value=-120.0, key="co_w")
                E = st.number_input("East", value=-110.0, key="co_e")

        # --- Date range input ---
        col1, col2 = st.columns(2)
        with col1:
            date_start = st.date_input("Start date", key="co_start")
        with col2:
            date_end = st.date_input("End date", key="co_end")

        # --- Clear-sky filter: the control with no methane equivalent ---
        # Dropping cloudy scenes (which only see the column above the cloud)
        # costs coverage, which is why it's a control and not a constant.
        with st.expander("Retrieval filter", expanded=False):
            clear_sky = st.checkbox(
                "Clear-sky only", value=CLEAR_SKY_DEFAULT, key="co_clear_sky",
                help="Keep only retrievals whose scattering layer sits below the "
                     "ceiling — the ones that reached near the surface. Off, the "
                     "page uses every pixel the product publishes, including "
                     "above-cloud columns that cannot see a ground source.",
            )
            ceiling = st.select_slider(
                "Cloud-height ceiling (m)", options=list(CLOUD_CEILING_CHOICES),
                value=DEFAULT_CLOUD_CEILING_M, key="co_ceiling",
                disabled=not clear_sky,
                help="Lower is stricter: more surface sensitivity, fewer valid "
                     "pixels. The availability chart below shows what the filter "
                     "costs on each day.",
            )
            st.caption(
                f"CO coverage starts {COVERAGE_START}. The filter is applied "
                "before anything else, so every number and every pixel on this "
                "page comes from the scenes it kept."
            )

        # The box the user is currently pointing at, so the map can follow the
        # selection even before a query is run.
        selected_bbox, bbox_error = resolve_bbox(region_name, city_name, N, S, W, E)
        selected_label = region_name or city_name or "Selected area"

        focus = ((selected_bbox["N"] + selected_bbox["S"]) / 2,
                 (selected_bbox["E"] + selected_bbox["W"]) / 2) if selected_bbox else None

        if st.button("Get CO column", type="primary", key="co_run"):
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
                    clear_sky=clear_sky, cloud_ceiling_m=ceiling,
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
                filter_text = (
                    f"clear-sky ≤ {result['cloud_ceiling_m']:.0f} m"
                    if result.get("cloud_ceiling_m") else "no cloud filter"
                )
                st.caption(f"{result_label} — {result['pass_count']} satellite "
                           f"passes · {filter_text}")

                # Read before the enhancement: it sets how much the enhancement is worth.
                if result.get("loading_note"):
                    st.markdown(
                        note(f"<b>Regional CO loading: "
                             f"{result['loading_level']}</b> — "
                             f"{result['loading_note']}",
                             result.get("loading_color")),
                        unsafe_allow_html=True,
                    )

                c1, c2, c3 = st.columns(3)
                c1.metric(f"Mean CO ({UNIT})", fmt(result.get("mean_co")))
                c2.metric(f"Background ({UNIT})", fmt(result.get("background_co")))
                # Percent is the headline: levels are assigned on it, not the
                # absolute column difference.
                c3.metric("Above background", fmt_pct(result.get("enhancement_pct")),
                          help="Percent of the local background column. The level "
                               "bands are assigned on this, because CO's "
                               "background moves with season and latitude and an "
                               "absolute cut would not travel.")
                level_delta(c3, result.get("level"), result.get("enhancement_pct"))

                st.caption(
                    f"In absolute terms: {fmt(result.get('enhancement_co'), signed=True)}"
                    f" {UNIT} above a background of {fmt(result.get('background_co'))}"
                    f" {UNIT}."
                )

                d1, d2, d3 = st.columns(3)
                d1.metric(f"Min ({UNIT})", fmt(result.get("min_co")))
                d2.metric(f"Median ({UNIT})", fmt(result.get("median_co")))
                d3.metric(f"Max ({UNIT})", fmt(result.get("max_co")))

                # Both tails trimmed before differencing, so a thin pass or a
                # single plume doesn't move the number.
                e1, e2, _ = st.columns(3)
                e1.metric(f"P10-P80 ({UNIT})",
                          fmt_range(result.get("p10_co"), result.get("p80_co"),
                                    digits=2))
                e2.metric(f"P10-P80 mean ({UNIT})", fmt(result.get("core_mean_co")),
                          help="Mean of the AOI pixels that fall inside P10-P80, "
                               "so the low and high tails are excluded.")

                g1, g2, g3 = st.columns(3)
                g1.metric(f"Background P10-P80 ({UNIT})",
                          fmt_range(result.get("bg_p10_co"),
                                    result.get("bg_p80_co"), digits=2),
                          help="The surrounding region's own percentiles, "
                               "measured over the same period.")
                g2.metric(f"Background P10-P80 mean ({UNIT})",
                          fmt(result.get("bg_core_mean_co")),
                          help="Mean of the surrounding region's pixels inside "
                               "its own P10-P80.")
                g3.metric("P10-P80 above bg",
                          fmt_pct(result.get("core_enhancement_pct")),
                          help="The two P10-P80 means differenced, as a percent: "
                               "the AOI's bulk level against the background's, "
                               "with both tails off each side.")
                level_delta(g3, result.get("core_level"),
                            result.get("core_enhancement_pct"))

                # Hot end gets the same above-background comparison, since a
                # small plume barely moves the area mean.
                f1, f2, f3 = st.columns(3)
                f1.metric("Hotspot above bg",
                          fmt_pct(result.get("hotspot_enhancement_pct")),
                          help="Hottest fifth of the pixels (P80) against local "
                               "background.")
                level_delta(f1, result.get("hotspot_level"),
                            result.get("hotspot_enhancement_pct"))
                f2.metric("Peak above bg",
                          fmt_pct(result.get("peak_enhancement_pct")),
                          help="Highest single pixel value against local "
                               "background.")
                hotspots = result.get("hotspots")
                if hotspots:
                    hottest = hotspots[0]
                    found = result.get("hotspot_region_count") or len(hotspots)
                    # Show what the map shows, not just the raw total found.
                    shown_text = (f"{len(hotspots)}" if found <= len(hotspots)
                                  else f"{len(hotspots)} of {found}")
                    top = hottest.get("enhancement_pct")
                    f3.metric(
                        "Hotspot regions boxed", shown_text,
                        delta=(f"{top:+.1f}% top patch" if top is not None
                               else None),
                        delta_color="inverse",
                        help=f"{found} contiguous patch(es) of above-P80 pixels "
                             f"were found inside the AOI; the {len(hotspots)} "
                             "with the highest mean are boxed on the map, "
                             "numbered hottest first. A large AOI breaks its hot "
                             "tail into many patches, so only the strongest are "
                             "drawn.",
                    )

        if stale:
            st.info(f"Press *Get CO column* to load **{selected_label}**.")

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
                    key="co_hotspot_count",
                    help=(f"Ranked by patch mean, hottest first. {available} "
                          "patches are available; the rest are weaker and "
                          "clutter the raster."),
                )
            st_folium(build_result_map(result, max_hotspots=shown),
                      use_container_width=True, height=MAP_HEIGHT,
                      returned_objects=[], key=f"co_map_{shown}")
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
                       "carbon monoxide over it.")

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
        st.subheader("Daily mean CO")
        if result and not result["error"] and result.get("series"):
            st.altair_chart(build_series_chart(result), use_container_width=True)
            st.markdown(level_legend_html(), unsafe_allow_html=True)
        elif result and not result["error"]:
            st.info("No daily values available for this area and date range.")
        else:
            st.info("Run a query to plot the CO column over time.")

    with availability_col:
        st.subheader("Daily data availability")
        if result and not result["error"] and result.get("availability"):
            st.altair_chart(build_availability_chart(result),
                            use_container_width=True)
            st.caption(
                "Pixels of the box sampled each day, split into the retrievals "
                "kept and the ones removed. For CO that removal is the product's "
                "quality mask plus the clear-sky filter when it is on — the "
                "latter is usually the larger share, and is the price of the "
                "surface sensitivity it buys."
            )
            st.markdown(loading_legend_html(), unsafe_allow_html=True)
        elif result and not result["error"]:
            st.info("No per-day pixel counts available for this area and date "
                    "range.")
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

    # --- How this reads next to the other gases -------------------------------
    st.divider()
    st.subheader("Reading CO against methane")
    st.markdown(
        "CO and CH4 are retrieved from the same shortwave-infrared detector on "
        "the same Sentinel-5P overpass, so a given day's readings come from the "
        "same photons — there is no co-location or timing error between them. "
        "That is what makes the pair diagnostic rather than merely two charts:"
    )
    st.markdown(
        "- **CH4 elevated and CO elevated** — combustion. Flaring, an engine, or "
        "a fire.\n"
        "- **CH4 elevated and CO flat** — a fugitive leak: gas escaping unburnt.\n"
        "- **CO elevated and CH4 flat** — combustion of something that is not "
        "natural gas, most often biomass.\n\n"
        "Run the same area and dates on both agents to make that comparison. "
        "Check the regional-loading banner first: in a smoky month CO is "
        "elevated everywhere, and only the *enhancement above local background* "
        "carries information."
    )
    st.page_link("ch4/frontend.py",
                 label="Open the Methane agent for this area",
                 icon=":material/local_fire_department:")
