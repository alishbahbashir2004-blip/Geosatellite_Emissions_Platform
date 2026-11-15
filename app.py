# app.py

import streamlit as st

from gas_registry import live_gases, planned_gases

DASHBOARD = "dashboard.py"


def _page_map():
    """Router pages, grouped the way the sidebar should list them.

    Only gases with a `page` become routes; unbuilt ones stay on the
    dashboard as greyed-out cards.
    """
    dashboard = st.Page(
        DASHBOARD, title="Dashboard", icon=":material/space_dashboard:",
        url_path="dashboard", default=True,
    )
    agents = [
        st.Page(gas.page, title=f"{gas.name} ({gas.formula})", icon=gas.icon,
                url_path=gas.key)
        for gas in live_gases()
    ]
    return {"": [dashboard], "Gas agents": agents}


def _sidebar():
    """Shared navigation, drawn around whichever page just ran."""
    with st.sidebar:
        st.markdown(
            "<div style='font-weight:700;font-size:1.05rem;line-height:1.3;'>"
            "Emissions Intelligence</div>"
            "<div style='opacity:0.6;font-size:0.8rem;padding-bottom:0.5rem;'>"
            "Sentinel-5P · OCO-2/3 · NASA GHG Center</div>",
            unsafe_allow_html=True,
        )
        st.page_link(DASHBOARD, label="Dashboard",
                     icon=":material/space_dashboard:")
        st.caption("GAS AGENTS")
        for gas in live_gases():
            st.page_link(gas.page, label=f"{gas.formula} · {gas.name}",
                         icon=gas.icon)

        upcoming = planned_gases()
        if upcoming:
            st.caption("NOT BUILT YET")
            st.markdown(
                "<div style='opacity:0.45;font-size:0.82rem;line-height:1.9;'>"
                + "".join(f"{gas.formula} · {gas.name}<br>" for gas in upcoming)
                + "</div>",
                unsafe_allow_html=True,
            )


# Order matters — see the note at the top of the file.
page = st.navigation(_page_map(), position="hidden")
page.run()
_sidebar()
