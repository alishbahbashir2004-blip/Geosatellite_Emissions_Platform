# dashboard.py
# Landing page: reads gas_registry.py and draws a card per gas. A new gas
# appears here without editing this file.

import streamlit as st

from gas_registry import GASES

st.set_page_config(page_title="Emissions Intelligence — Dashboard",
                   page_icon=":material/satellite_alt:", layout="wide")

# Same hairline the charts use — works in both light and dark themes.
HAIRLINE = "rgba(128,128,128,0.25)"

CARD_CSS = """
<style>
.gas-head { display:flex; align-items:center; gap:0.6rem; margin-bottom:0.7rem; }
.gas-badge {
  font: 700 0.9rem/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  padding: 0.34rem 0.5rem; border-radius: 6px; color: #fff; flex: none;
  letter-spacing: 0.02em;
}
.gas-name { font-weight: 650; font-size: 1.06rem; line-height: 1.2; }
.gas-meta {
  font: 0.75rem/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
  opacity: 0.55; margin-bottom: 0.55rem;
}
.gas-chips { display:flex; flex-wrap:wrap; gap:0.3rem; margin-bottom:0.2rem; }
.gas-chip {
  font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em;
  border: 1px solid %(hairline)s; border-radius: 999px;
  padding: 0.12rem 0.5rem; opacity: 0.75;
}
.gas-soon { opacity: 0.5; }
</style>
""" % {"hairline": HAIRLINE}

st.markdown(CARD_CSS, unsafe_allow_html=True)

st.markdown(
    "<h1 style='text-align:center;margin-bottom:0;'>"
    "Satellite Emissions Intelligence</h1>"
    "<p style='text-align:center;font-size:1.05rem;opacity:0.65;"
    "margin:0.4rem 0 0.2rem;'>"
    "Per-gas agents over Sentinel-5P, each measuring a region against its own "
    "local background</p>"
    "<p style='text-align:center;font-size:0.9rem;opacity:0.5;margin-top:0;'>"
    "Pick a gas to open its agent. Every gas runs its own pipeline, its own "
    "thresholds and its own map.</p>",
    unsafe_allow_html=True,
)

st.divider()


def gas_card(gas):
    """One card. Live gases get a button into their page; the rest are inert."""
    dim = "" if gas.page else " gas-soon"
    with st.container(border=True):
        st.markdown(
            f"<div class='gas-head{dim}'>"
            f"<span class='gas-badge' style='background:{gas.accent};'>"
            f"{gas.formula}</span>"
            f"<span class='gas-name'>{gas.name}</span></div>"
            f"<div class='gas-meta'>{gas.product}<br>"
            f"{gas.unit} · data from {gas.since}</div>"
            "<div class='gas-chips'>"
            + "".join(f"<span class='gas-chip'>{s}</span>" for s in gas.sdgs)
            + "</div>",
            unsafe_allow_html=True,
        )
        if gas.page:
            if st.button(f"Open {gas.name} agent", key=f"open_{gas.key}",
                         type="primary", use_container_width=True):
                # Clears any remembered view so opening from the dashboard
                # always lands on the gas's own landing page (sidebar nav
                # should still restore the last view, so don't clear there).
                st.session_state.pop(f"{gas.key}_view", None)
                st.switch_page(gas.page)
        else:
            st.button("Not built yet", key=f"soon_{gas.key}", disabled=True,
                      use_container_width=True,
                      help="Declared in gas_registry.py with no page behind "
                           "it. Add its folder, point `page` at it, and this "
                           "card becomes live.")


# Two per row.
for row_start in range(0, len(GASES), 2):
    columns = st.columns(2, gap="large")
    for column, gas in zip(columns, GASES[row_start:row_start + 2]):
        with column:
            gas_card(gas)
