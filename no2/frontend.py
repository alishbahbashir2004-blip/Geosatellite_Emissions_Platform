# no2/frontend.py
# Dispatcher: sets page config, then draws whichever view is picked. Lives
# here, not per-view, since Streamlit allows set_page_config() only once per run.

import streamlit as st

st.set_page_config(page_title="Nitrogen Dioxide Agent",
                   page_icon=":material/factory:", layout="wide")

from no2 import compare, home, single_area

# What each view is drawn by. A view missing here falls back to the cards
# instead of a blank page.
VIEWS = {
    home.SINGLE: single_area.render,
    home.COMPARE: compare.render,
}

view = st.session_state.get(home.VIEW_KEY, home.HOME)
draw = VIEWS.get(view)

if draw is None:
    home.render()
else:
    # Back out to the cards; drawn first so it sits at the top, narrow so it
    # reads as chrome rather than a view control.
    back_col, _ = st.columns([1, 4])
    if back_col.button("← All NO2 tools", key="no2_back",
                       use_container_width=True):
        st.session_state[home.VIEW_KEY] = home.HOME
        st.rerun()
    draw()
