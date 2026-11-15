# no2/compare.py
# Two areas measured against each other: pick two cities or two regions, one
# date range, and read their NO2 side by side on one map.
#
# No background, anywhere
# -----------------------
# This page runs `run_area_pipeline`, not the single-area one. That pipeline
# computes no padded reference box, no enhancement and no level — each area is
# described purely on its own terms, and the other area is the only thing it
# is read against. Nothing here can report a background because nothing
# upstream computes one. No percent-of-background either, for the same
# reason: there is no background to take a percentage of, so every number on
# this page is in µmol/m², not %.
#
# That also fixes what a hotspot means on this page. A patch is boxed because
# it beats *its own area's* P80 — the hot fifth of that area's own pixels — so
# the count is "how many distinct hot patches does this area have", which is a
# statement about the area alone and therefore comparable across the two.
#
# Each area also gets two charts under its card: its pixel histogram, banded
# on its own P10-P80, because two areas can share a mean and share nothing
# else and the shape is what says so; and its daily pixel availability,
# because the two areas' numbers are only as comparable as the data behind
# them — NO2 is retrieved in the visible, so a cloudy area can lose far more
# of its pixels than a clear one.
#
# Like/like only: cities compare to cities and regions to regions, because a
# city AOI is a 0.3-degree box around a point and a region is a province.
# Putting one against the other would compare a neighbourhood to a prairie and
# read the difference as a finding. The kind radio is what enforces it — there
# is no control that can mix them.

import time

import streamlit as st
from streamlit_folium import st_folium

from shared.regions import REGIONS
from shared.cities import CITIES
from shared.globeview import render_globe, ZOOM_SECONDS
# `fmt` is bound to this gas's own precision rather than left on shared/ui's
# flat two decimals. The digit count is the one the gas already declares in
# its chartview SPEC, so a metric and a chart tooltip never disagree about the
# same number. No call site below passes `digits` positionally, so this
# reaches all of them.
from functools import partial as _partial
from shared.ui import fmt as _fmt
from shared.ui import fmt_range, level_delta
from no2.chartview import SPEC as _CHART_SPEC

fmt = _partial(_fmt, digits=_CHART_SPEC.digits)
from no2.backend import run_area_pipeline
from no2.config import UNIT, DEFAULT_HOTSPOT_REGIONS
from no2.chartview import build_availability_chart, build_histogram_chart
from no2.mapview import build_compare_map

MAP_HEIGHT = 430

# Namespaced apart from the single-area page's key, so a comparison and a
# single run can both sit in the session without overwriting each other.
RESULT_KEY = "no2_compare_result"

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


def _run(kind, label, date_start, date_end):
    """One area through the background-free pipeline.

    Both areas go through the same call with the same dates, so the only thing
    that differs between the two results is the ground underneath them.
    """
    if kind == CITIES_KIND:
        return run_area_pipeline(city_name=label, date_start=date_start,
                                 date_end=date_end)
    return run_area_pipeline(region_name=label, date_start=date_start,
                             date_end=date_end)


def _stat_card(area, other):
    """One area's numbers. Every figure here describes this area alone.

    `other` is the area this one is being read against — its label goes on the
    difference metric, and its mean is what that difference is taken from.
    That difference is the only number on the card that looks outside this
    area at all.
    """
    result, label = area["result"], area["label"]
    mean, other_mean = result.get("mean_no2"), other["result"].get("mean_no2")

    with st.container(border=True):
        st.caption(f"{label} — {result['pass_count']} satellite passes")

        a1, a2, a3 = st.columns(3)
        a1.metric(f"Mean NO2 ({UNIT})", fmt(mean))

        # The head-to-head: on this page the other area is the only reference.
        difference = (None if mean is None or other_mean is None
                      else mean - other_mean)
        a2.metric(f"vs {other['label']}", fmt(difference, signed=True),
                  help=f"This area's mean column minus {other['label']}'s, in "
                       f"{UNIT}.")
        if difference is not None:
            level_delta(a2, f"Higher than {other['label']}" if difference >= 0
                        else f"Lower than {other['label']}", difference)

        # Patches that beat this area's own P80 — the hot fifth of its own
        # pixels. No outside reference is involved in finding or ranking them.
        hotspots = result.get("hotspots") or []
        found = result.get("hotspot_region_count") or len(hotspots)
        shown_text = (f"{len(hotspots)}" if found <= len(hotspots)
                      else f"{len(hotspots)} of {found}")
        hottest = hotspots[0] if hotspots else None
        cut = result.get("p80_no2")
        a3.metric(
            "Hotspot regions (> own P80)", shown_text if hotspots else "0",
            delta=(fmt(hottest.get("above_cut_no2"), digits=1, signed=True)
                   + f" {UNIT} top patch")
            if hottest and hottest.get("above_cut_no2") is not None else None,
            delta_color="inverse",
            help=f"{found} contiguous patch(es) of this area's pixels sit "
                 + (f"above its own P80 of {cut:.1f} {UNIT}"
                    if cut is not None else "above its own P80")
                 + ". The cut is this area's own hot-fifth threshold, so the "
                   "count says how broken-up its hot tail is — nothing "
                   "outside the area is involved.",
        )

        # How the column varies across the pixels of the box.
        b1, b2, b3 = st.columns(3)
        b1.metric(f"Min ({UNIT})", fmt(result.get("min_no2")))
        b2.metric(f"Median ({UNIT})", fmt(result.get("median_no2")))
        b3.metric(f"Max ({UNIT})", fmt(result.get("max_no2")))

        core = result.get("core_mean_no2")
        other_core = other["result"].get("core_mean_no2")

        c1, c2, c3 = st.columns(3)
        c1.metric(f"P10-P80 ({UNIT})", fmt_range(result.get("p10_no2"),
                                                 result.get("p80_no2"),
                                                 digits=1))
        c2.metric(f"P10-P80 mean ({UNIT})", fmt(core),
                  help="Mean of this area's pixels inside P10-P80, so the low "
                       "and high tails are excluded. The steadier of the two "
                       "means to compare areas on.")

        # The same head-to-head as `vs <other>` above, on the tail-trimmed
        # means instead of the plain ones. Worth having both: when the two
        # disagree in sign, the gap between the areas is being carried by one
        # side's tails rather than by the bulk of its pixels.
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
    """The area's pixel histogram, drawn under its own card.

    The same figure as the single-area page's "AOI P10-P80 histogram", banded
    on this area's own P10-P80 — so like everything else on this page it needs
    no background. One per area, because two areas can share a mean and still
    have nothing else in common: a broad flat spread and a narrow spike read
    identically as a single number and obviously differently as a shape.

    The middle band falls back to a neutral grey here rather than carrying a
    level colour, because there is no level on this page to colour it by.
    """
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
    """The area's per-day pixel coverage, under its own card.

    The same figure as the single-area page's "Daily data availability". It
    earns its place in a comparison specifically: the two areas' numbers are
    only as comparable as the data behind them, and NO2 is retrieved in the
    visible, so a cloudy area can end up with far fewer surviving pixels than
    a clear one even over the identical date range.
    """
    result = area["result"]
    st.markdown(f"**{area['label']} — daily data availability**")
    if not result.get("availability"):
        st.info("No per-day pixel counts available for this area.")
        return
    st.altair_chart(build_availability_chart(result), use_container_width=True)
    st.caption(
        "Pixels of the box sampled each day, split into valid retrievals and "
        "the ones cloud and quality masking removed. Days with a thin valid "
        "band carry very few pixels behind them."
    )


def _verdict(areas):
    """One line above the cards saying which area came out higher."""
    first, second = areas
    a, b = first["result"].get("mean_no2"), second["result"].get("mean_no2")
    if a is None or b is None:
        return
    high, low = (first, second) if a >= b else (second, first)

    # The tail-trimmed means too, because a single plume or a partly clouded
    # pass can move a plain mean without the bulk of either area shifting.
    core_high = high["result"].get("core_mean_no2")
    core_low = low["result"].get("core_mean_no2")
    tail = ""
    if core_high is not None and core_low is not None:
        tail = (f" On P10-P80 means, with both tails trimmed: "
                f"{high['label']} {core_high:.1f}, {low['label']} "
                f"{core_low:.1f} {UNIT}.")

    st.markdown(
        f"<div style='font-size:0.95rem;line-height:1.6;border-left:3px solid "
        f"#8e6bbf;padding:0.45rem 0 0.45rem 0.8rem;'>"
        f"<b>{high['label']}</b> has the higher mean column — "
        f"<b>{abs(a - b):.1f} {UNIT}</b> above {low['label']}.{tail}</div>",
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

    # The map column's slot is claimed before the controls are drawn: Streamlit
    # renders by column rather than by code order, so the globe can be written
    # here from inside the controls block below and still land on the right —
    # which is what lets it spin while the two queries block.
    with map_col:
        st.subheader("Map")
        map_slot = st.empty()

    with controls_col:
        st.subheader("Areas & date range")

        kind = st.radio("What do you want to compare?",
                        [REGIONS_KIND, CITIES_KIND], horizontal=True,
                        key="no2_cmp_kind",
                        help="Like for like only. A city AOI is a small box "
                             "around a point and a region is a province, so "
                             "the two are never offered against each other.")

        options = (_city_options() if kind == CITIES_KIND
                   else sorted(REGIONS.keys()))
        noun = "City" if kind == CITIES_KIND else "Region"

        col1, col2 = st.columns(2)
        with col1:
            label_a = st.selectbox(f"{noun} 1", options, index=0,
                                   key=f"no2_cmp_a_{kind}")
        with col2:
            label_b = st.selectbox(f"{noun} 2", options,
                                   index=1 if len(options) > 1 else 0,
                                   key=f"no2_cmp_b_{kind}")

        col1, col2 = st.columns(2)
        with col1:
            date_start = st.date_input("Start date", key="no2_cmp_start")
        with col2:
            date_end = st.date_input("End date", key="no2_cmp_end")

        same = label_a == label_b
        if same:
            st.warning(f"Pick two different {noun.lower()}s to compare.")

        if st.button("Get NO2 column", type="primary",
                     key="no2_cmp_run", disabled=same):
            # Spin the globe up first. Streamlit flushes each element as the
            # script produces it, so this reaches the browser and animates for
            # the length of both Earth Engine calls rather than after them.
            anchor = time.time()
            with map_slot.container():
                render_globe(phase="launch", height=MAP_HEIGHT, anchor=anchor)

            areas = []
            for label in (label_a, label_b):
                with st.spinner(f"Querying Google Earth Engine for {label}..."):
                    areas.append({
                        "label": label,
                        "result": _run(kind, label, str(date_start),
                                       str(date_end)),
                    })
            st.session_state[RESULT_KEY] = {"kind": kind, "areas": areas}

            # Land on the first area before handing over to the map — the same
            # one the map's radio starts on. The shared `anchor` lets the
            # push-in pick the spin up mid-turn instead of restarting it.
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
            # Redraw from the top so the map lands in the slot the globe is
            # currently holding, through the ordinary result path below.
            st.rerun()

    stored = st.session_state.get(RESULT_KEY)
    areas = (stored or {}).get("areas") or []
    failed = [a for a in areas if a["result"].get("error")]
    usable = bool(areas) and not failed

    # Filling the slot claimed above. A finished comparison gets the real map;
    # anything else — nothing run yet, or one of the two areas failed — falls
    # back to the globe.
    with map_slot.container():
        if usable:
            # Only one raster can be on the map at a time, so the reader picks
            # which. Both areas' outlines and hotspot boxes stay up either way,
            # on their own toggles in the layer control.
            labels = [a["label"] for a in areas]
            picked = st.radio("Show raster for", labels, horizontal=True,
                              key="no2_cmp_map_pick")
            selected = labels.index(picked)
            st_folium(
                build_compare_map(areas, selected=selected,
                                  max_hotspots=DEFAULT_HOTSPOT_REGIONS),
                use_container_width=True, height=MAP_HEIGHT,
                returned_objects=[], key=f"no2_cmp_map_{selected}",
            )
            st.caption(
                "Only the selected area's raster is drawn — there is no "
                "surrounding-area layer, because neither area is measured "
                "against a background here. The green boxes mark patches "
                "above each area's own P80; both areas' boxes are in the "
                "layer control."
            )
        else:
            render_globe(phase="idle", height=MAP_HEIGHT)
            st.caption("Pick two areas and a date range, then run a query to "
                       "map nitrogen dioxide over both.")

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
