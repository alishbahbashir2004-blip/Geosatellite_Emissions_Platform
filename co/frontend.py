# co/frontend.py
# CO page the router runs: sets page config, then dispatches to
# home/single_area/compare — set_page_config() must run first, so views don't call it.

import streamlit as st

st.set_page_config(page_title="Carbon Monoxide Agent",
                   page_icon=":material/mode_heat:", layout="wide")

from co import compare, home, single_area

# What each view is drawn by. No entry here falls back to the cards, so a
# half-added view lands somewhere sensible rather than a blank page.
VIEWS = {
    home.SINGLE: single_area.render,
    home.COMPARE: compare.render,
}

view = st.session_state.get(home.VIEW_KEY, home.HOME)
draw = VIEWS.get(view)

if draw is None:
    home.render()
else:
    # Narrow column so the back button reads as chrome, not a view control.
    back_col, _ = st.columns([1, 4])
    if back_col.button("← All CO tools", key="co_back",
                       use_container_width=True):
        st.session_state[home.VIEW_KEY] = home.HOME
        st.rerun()
    draw()
