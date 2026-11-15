# co/compare.py
# Two areas vs. each other on one map. Runs run_area_pipeline (no background/
# enhancement/loading); one clear-sky filter for both — differing filters would misread as a ground difference.

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
from shared.ui import fmt_range, level_delta
from co.chartview import SPEC as _CHART_SPEC

fmt = _partial(_fmt, digits=_CHART_SPEC.digits)
from co.backend import run_area_pipeline
from co.config import (UNIT, DEFAULT_HOTSPOT_REGIONS, CLEAR_SKY_DEFAULT,
                       DEFAULT_CLOUD_CEILING_M, CLOUD_CEILING_CHOICES,
                       COVERAGE_START)
from co.chartview import build_availability_chart, build_histogram_chart
from co.mapview import build_compare_map

MAP_HEIGHT = 430

# Namespaced apart from the single-area page's key, so a comparison and a
# single run can both sit in the session without overwriting each other.
RESULT_KEY = "co_compare_result"

CITIES_KIND = "Cities"
REGIONS_KIND = "Regions"


def _city_options():
    """CITIES may be a dict (name -> meta) or a list of {name, lat, lon}."""
    if isinstance(CITIES, dict):
        return sorted(CITIES.keys())
    if isinstance(CITIES, list):
        return sorted(
            (c.get("name") if isinstance(c, dict) and c.get("name") else str(c))
            for c in CITIES
        )
    return [str(CITIES)]


def _run(kind, label, date_start, date_end, clear_sky, ceiling):
    """One area through the background-free pipeline. Both areas use the
    same dates and the same clear-sky filter."""
    common = dict(date_start=date_start, date_end=date_end,
                  clear_sky=clear_sky, cloud_ceiling_m=ceiling)
    if kind == CITIES_KIND:
        return run_area_pipeline(city_name=label, **common)
    return run_area_pipeline(region_name=label, **common)


def _stat_card(area, other):
    """One area's numbers. `other` is only used for the two head-to-head
    difference metrics; every other figure describes this area alone."""
    result, label = area["result"], area["label"]
    mean, other_mean = result.get("mean_co"), other["result"].get("mean_co")

    with st.container(border=True):
        filter_text = (f"clear-sky ≤ {result['cloud_ceiling_m']:.0f} m"
                       if result.get("cloud_ceiling_m") else "no cloud filter")
        st.caption(f"{label} — {result['pass_count']} satellite passes · "
                   f"{filter_text}")

        a1, a2, a3 = st.columns(3)
        a1.metric(f"Mean CO ({UNIT})", fmt(mean))

        difference = (None if mean is None or other_mean is None
                      else mean - other_mean)
        a2.metric(f"vs {other['label']}", fmt(difference, signed=True),
                  help=f"This area's mean column minus {other['label']}'s, in "
                       f"{UNIT}.")
        if difference is not None:
            level_delta(a2, f"Higher than {other['label']}" if difference >= 0
                        else f"Lower than {other['label']}", difference)

        # Patches beating this area's own P80 — no outside reference involved.
        hotspots = result.get("hotspots") or []
        found = result.get("hotspot_region_count") or len(hotspots)
        shown_text = (f"{len(hotspots)}" if found <= len(hotspots)
                      else f"{len(hotspots)} of {found}")
        hottest = hotspots[0] if hotspots else None
        cut = result.get("p80_co")
        a3.metric(
            "Hotspot regions (> own P80)", shown_text if hotspots else "0",
            delta=(fmt(hottest.get("above_cut_co"), digits=2, signed=True)
                   + f" {UNIT} top patch")
            if hottest and hottest.get("above_cut_co") is not None else None,
            delta_color="inverse",
            help=f"{found} contiguous patch(es) of this area's pixels sit "
                 + (f"above its own P80 of {cut:.2f} {UNIT}"
                    if cut is not None else "above its own P80")
                 + ". The cut is this area's own hot-fifth threshold, so the "
                   "count says how broken-up its hot tail is — nothing "
                   "outside the area is involved.",
        )

        b1, b2, b3 = st.columns(3)
        b1.metric(f"Min ({UNIT})", fmt(result.get("min_co")))
        b2.metric(f"Median ({UNIT})", fmt(result.get("median_co")))
        b3.metric(f"Max ({UNIT})", fmt(result.get("max_co")))

        core = result.get("core_mean_co")
        other_core = other["result"].get("core_mean_co")

        c1, c2, c3 = st.columns(3)
        c1.metric(f"P10-P80 ({UNIT})", fmt_range(result.get("p10_co"),
                                                 result.get("p80_co"),
                                                 digits=2))
        c2.metric(f"P10-P80 mean ({UNIT})", fmt(core),
                  help="Mean of this area's pixels inside P10-P80, so the low "
                       "and high tails are excluded. The steadier of the two "
                       "means to compare areas on.")

        # Same head-to-head as `vs <other>` above, but tail-trimmed: a sign
        # disagreement means the gap is carried by one side's tails, not its bulk.
        core_difference = (None if core is None or other_core is None
                           else core - other_core)
        c3.metric(f"vs {other['label']}'s P10-P80 mean",
                  fmt(core_difference, signed=True),
                  help=f"This area's P10-P80 mean minus {other['label']}'s, in "
                       f"{UNIT}. Both tails are off each side, so this is the "
                       "bulk-against-bulk comparison.")
        if core_difference is not None:
            level_delta(c3,
                        f"Higher than {other['label']}" if core_difference >= 0
                        else f"Lower than {other['label']}", core_difference)


def _distribution(area):
    """The area's pixel histogram, banded on its own P10-P80. One per area,
    since two areas can share a mean but differ entirely in shape."""
    result = area["result"]
    st.markdown(f"**{area['label']} — pixel distribution**")
    if not result.get("histogram"):
        st.info("No pixel distribution available for this area.")
        return
    st.altair_chart(build_histogram_chart(result), use_container_width=True)
    st.caption(
        "Every pixel of this area, split on its own P10-P80. The middle band "
        "holds 70% of them by construction; the tails are where a plume or a "
        "bad retrieval shows up."
    )


def _availability(area):
    """The area's per-day pixel coverage. Matters more than for methane: the
    same clear-sky filter can still leave two areas with very different data."""
    result = area["result"]
    st.markdown(f"**{area['label']} — daily data availability**")
    if not result.get("availability"):
        st.info("No per-day pixel counts available for this area.")
        return
    st.altair_chart(build_availability_chart(result), use_container_width=True)
    st.caption(
        "Pixels of the box sampled each day, split into the retrievals kept "
        "and the ones removed. For CO that removal is the product's quality "
        "mask plus the clear-sky filter when it is on — the latter is usually "
        "the larger share."
    )


def _verdict(areas):
    """One line above the cards saying which area came out higher."""
    first, second = areas
    a, b = first["result"].get("mean_co"), second["result"].get("mean_co")
    if a is None or b is None:
        return
    high, low = (first, second) if a >= b else (second, first)

    # Tail-trimmed means too, since a plume or thin pass can move a plain
    # mean without the bulk shifting.
    core_high = high["result"].get("core_mean_co")
    core_low = low["result"].get("core_mean_co")
    tail = ""
    if core_high is not None and core_low is not None:
        tail = (f" On P10-P80 means, with both tails trimmed: "
                f"{high['label']} {core_high:.2f}, {low['label']} "
                f"{core_low:.2f} {UNIT}.")

    st.markdown(
        f"<div style='font-size:0.95rem;line-height:1.6;border-left:3px solid "
        f"#e07b39;padding:0.45rem 0 0.45rem 0.8rem;'>"
        f"<b>{high['label']}</b> has the higher mean column — "
        f"<b>{abs(a - b):.2f} {UNIT}</b> above {low['label']}.{tail}</div>",
        unsafe_allow_html=True,
    )


def render():
    """Draw the two-area comparison page."""
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0;'>Compare areas</h1>"
        "<p style='text-align:center;font-size:1.05rem;opacity:0.65;"
        "margin-top:0.4rem;'>"
        f"Two cities or two regions, one date range, side by side in {UNIT}</p>",
        unsafe_allow_html=True,
    )

    controls_col, map_col = st.columns(2, gap="large")

    # Slot claimed before controls are drawn: Streamlit renders by column, not
    # code order, so the globe below still lands here and can spin.
    with map_col:
        st.subheader("Map")
        map_slot = st.empty()

    with controls_col:
        st.subheader("Areas & date range")

        kind = st.radio("What do you want to compare?",
                        [REGIONS_KIND, CITIES_KIND], horizontal=True,
                        key="co_cmp_kind",
                        help="Like for like only. A city AOI is a small box "
                             "around a point and a region is a province, so "
                             "the two are never offered against each other.")

        options = (_city_options() if kind == CITIES_KIND
                   else sorted(REGIONS.keys()))
        noun = "City" if kind == CITIES_KIND else "Region"

        col1, col2 = st.columns(2)
        with col1:
            label_a = st.selectbox(f"{noun} 1", options, index=0,
                                   key=f"co_cmp_a_{kind}")
        with col2:
            label_b = st.selectbox(f"{noun} 2", options,
                                   index=1 if len(options) > 1 else 0,
                                   key=f"co_cmp_b_{kind}")

        col1, col2 = st.columns(2)
        with col1:
            date_start = st.date_input("Start date", key="co_cmp_start")
        with col2:
            date_end = st.date_input("End date", key="co_cmp_end")

        # --- Clear-sky filter: one setting, applied to both areas ---
        with st.expander("Retrieval filter", expanded=False):
            clear_sky = st.checkbox(
                "Clear-sky only", value=CLEAR_SKY_DEFAULT,
                key="co_cmp_clear_sky",
                help="Keep only retrievals whose scattering layer sits below "
                     "the ceiling — the ones that reached near the surface. "
                     "Off, the page uses every pixel the product publishes, "
                     "including above-cloud columns that cannot see a ground "
                     "source.",
            )
            ceiling = st.select_slider(
                "Cloud-height ceiling (m)",
                options=list(CLOUD_CEILING_CHOICES),
                value=DEFAULT_CLOUD_CEILING_M, key="co_cmp_ceiling",
                disabled=not clear_sky,
                help="Lower is stricter: more surface sensitivity, fewer "
                     "valid pixels. The availability charts below show what "
                     "the filter cost each area.",
            )
            st.caption(
                f"CO coverage starts {COVERAGE_START}. One filter for both "
                "areas, on purpose — comparing an area filtered at one "
                "ceiling against one filtered at another would compare two "
                "different measurements."
            )

        same = label_a == label_b
        if same:
            st.warning(f"Pick two different {noun.lower()}s to compare.")

        if st.button("Get CO column", type="primary",
                     key="co_cmp_run", disabled=same):
            # Streamlit flushes each element as produced, so this animates
            # during both Earth Engine calls rather than after them.
            anchor = time.time()
            with map_slot.container():
                render_globe(phase="launch", height=MAP_HEIGHT, anchor=anchor)

            areas = []
            for label in (label_a, label_b):
                with st.spinner(f"Querying Google Earth Engine for {label}..."):
                    areas.append({
                        "label": label,
                        "result": _run(kind, label, str(date_start),
                                       str(date_end), clear_sky, ceiling),
                    })
            st.session_state[RESULT_KEY] = {"kind": kind, "areas": areas}

            # Lands on the first area (same one the map's radio starts on);
            # shared `anchor` lets the push-in pick up the spin mid-turn.
            first = areas[0]["result"]
            if first.get("bbox") and not first.get("error"):
                box = first["bbox"]
                with map_slot.container():
                    render_globe(phase="zoom",
                                 focus=((box["N"] + box["S"]) / 2,
                                        (box["E"] + box["W"]) / 2),
                                 height=MAP_HEIGHT, anchor=anchor,
                                 zoom_at=time.time())
                time.sleep(ZOOM_SECONDS)
            st.rerun()

    stored = st.session_state.get(RESULT_KEY)
    areas = (stored or {}).get("areas") or []
    failed = [a for a in areas if a["result"].get("error")]
    usable = bool(areas) and not failed

    # Filling the slot claimed above: a finished comparison gets the real map,
    # anything else falls back to the globe.
    with map_slot.container():
        if usable:
            # Only one raster can be on the map at a time, so the reader picks.
            labels = [a["label"] for a in areas]
            picked = st.radio("Show raster for", labels, horizontal=True,
                              key="co_cmp_map_pick")
            selected = labels.index(picked)
            st_folium(
                build_compare_map(areas, selected=selected,
                                  max_hotspots=DEFAULT_HOTSPOT_REGIONS),
                use_container_width=True, height=MAP_HEIGHT,
                returned_objects=[], key=f"co_cmp_map_{selected}",
            )
            st.caption(
                "Only the selected area's raster is drawn — there is no "
                "surrounding-area layer, because neither area is measured "
                "against a background here. The cyan boxes mark patches "
                "above each area's own P80; both areas' boxes are in the "
                "layer control."
            )
        else:
            render_globe(phase="idle", height=MAP_HEIGHT)
            st.caption("Pick two areas and a date range, then run a query to "
                       "map carbon monoxide over both.")

    # --- Results, full width below the map -----------------------------------
    st.divider()

    if not areas:
        st.info("Run a comparison to see both areas' numbers side by side.")
        return

    for area in failed:
        st.error(f"{area['label']}: {area['result']['error']}")
    if failed:
        return

    _verdict(areas)
    st.write("")

    for column, area, other in zip(st.columns(2, gap="large"),
                                   areas, reversed(areas)):
        with column:
            _stat_card(area, other)
            st.write("")
            _distribution(area)
            st.write("")
            _availability(area)
