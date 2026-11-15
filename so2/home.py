# so2/home.py
# What the SO2 agent opens on: a card per thing it can do. Picking one writes
# its name into VIEW_KEY and the page redraws into that view.
#
# The cards live here rather than in shared/ because what the SO2 agent can do
# is a statement about sulphur dioxide. The grid that draws them is generic
# and comes from shared/chooser.py, so each gas gets its own landing page by
# declaring its own cards and nothing else.

import streamlit as st

from shared.chooser import ModeCard, render as render_cards
from so2.config import UNIT

# Which view the page is currently showing. Namespaced like every other SO2
# session key, so each gas's landing page keeps its own place. The dashboard
# clears this key on its "Open ... agent" button, so that button always lands
# here.
VIEW_KEY = "so2_view"

HOME = "home"
SINGLE = "single"
COMPARE = "compare"

CARDS = (
    ModeCard(
        view=SINGLE,
        badge="1",
        title="Single area",
        blurb="Measure one region, city or bounding box against the "
              f"surrounding area over a date range. Mean SO2 in {UNIT}, how "
              "far it sits above its own local background, and where the hot "
              "patches are — with the noise caveat this product needs.",
        button="Get SO2 column",
        accent="#4b8b9b",
    ),
    ModeCard(
        view=COMPARE,
        badge="2",
        title="Compare cities / regions",
        blurb="Put two cities, or two regions, side by side over the same "
              "dates. Which sits higher and by how much, how each area's "
              "pixels are spread, and how many hot patches each carries.",
        button="Compare areas",
        accent="#4b8b9b",
    ),
)


def render():
    """Draw the landing cards."""
    st.markdown(
        "<h1 style='text-align:center;margin-bottom:0;'>Sulphur Dioxide "
        "Agent</h1>"
        "<p style='text-align:center;font-size:1.05rem;opacity:0.65;"
        "margin:0.4rem 0 0.2rem;'>"
        f"Sentinel-5P SO2 column ({UNIT}) from Google Earth Engine</p>"
        "<p style='text-align:center;font-size:0.9rem;opacity:0.5;"
        "margin-top:0;'>What would you like to do?</p>",
        unsafe_allow_html=True,
    )
    st.divider()
    render_cards(CARDS, VIEW_KEY, columns=2, key_prefix="so2_mode_card")
