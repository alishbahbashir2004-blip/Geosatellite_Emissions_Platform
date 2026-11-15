# ch4/home.py
# Landing page: a card per thing the agent can do. Picking one writes its
# name into VIEW_KEY; the grid itself is generic (shared/chooser.py).

import streamlit as st

from shared.chooser import ModeCard, render as render_cards
from ch4.config import UNIT

# Which view the page is showing; namespaced per gas. Dashboard clears this
# key on its "Open ... agent" button, so that button always lands here.
VIEW_KEY = "ch4_view"

HOME = "home"
SINGLE = "single"
COMPARE = "compare"

CARDS = (
    ModeCard(
        view=SINGLE,
        badge="1",
        title="Single area",
        blurb="Measure one region, city or bounding box against the "
              f"surrounding area over a date range. Mean CH4 in {UNIT}, how "
              "far it sits above its own local background, where the hot "
              "patches are, and how the pixels are distributed.",
        button="Get CH4 concentration",
        accent="#d32f2f",
    ),
    ModeCard(
        view=COMPARE,
        badge="2",
        title="Compare cities / regions",
        blurb="Put two cities, or two regions, side by side over the same "
              "dates. Which sits higher and by how much, how each area's "
              "pixels are spread, and how many hot patches each carries — "
              "the comparison a single run cannot make.",
        button="Compare areas",
        accent="#8e6bbf",
    ),
)


def render():
    """Draw the landing cards."""
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0;'>Methane Emission "
        "Agent</h1>"
        "<p style='text-align:center;font-size:1.05rem;opacity:0.65;"
        "margin:0.4rem 0 0.2rem;'>"
        "Sentinel-5P CH4 from Google Earth Engine, measured against local "
        "background</p>"
        "<p style='text-align:center;font-size:0.9rem;opacity:0.5;"
        "margin-top:0;'>What would you like to do?</p>",
        unsafe_allow_html=True,
    )
    st.divider()
    render_cards(CARDS, VIEW_KEY, columns=2, key_prefix="ch4_mode_card")
