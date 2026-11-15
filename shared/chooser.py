# shared/chooser.py
# The card grid a gas page opens on: one card per view, button switches to it.
# Gas-agnostic — a gas declares its cards and its view-state session key.

import streamlit as st
from dataclasses import dataclass

# Namespaced apart from the dashboard's card CSS. `min-height` on the blurb
# keeps buttons row-aligned when one card's text runs a line longer.
CARD_CSS = """
<style>
.mode-head { display:flex; align-items:center; gap:0.6rem; margin-bottom:0.7rem; }
.mode-badge {
  font: 700 0.9rem/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  padding: 0.34rem 0.5rem; border-radius: 6px; color: #fff; flex: none;
  letter-spacing: 0.02em;
}
.mode-title { font-weight: 650; font-size: 1.06rem; line-height: 1.2; }
.mode-blurb {
  font-size: 0.88rem; line-height: 1.6; opacity: 0.7;
  margin-bottom: 0.7rem; min-height: 4.4em;
}
.mode-soon { opacity: 0.5; }
</style>
"""


@dataclass(frozen=True)
class ModeCard:
    """One thing an agent can do, as a card on its landing page. `view` is
    written to the page's view key on click; `enabled=False` greys it out."""
    view: str
    badge: str            # short label in the accent-coloured chip
    title: str
    blurb: str            # one or two lines: what this view answers
    button: str           # button label when the view is available
    accent: str           # hex, the badge colour
    enabled: bool = True
    soon_help: str = ""   # tooltip on the dead button, when not enabled


def render(cards, view_key, columns=2, key_prefix="mode"):
    """Draw the cards. Picking one stores its view and reruns the page."""
    st.markdown(CARD_CSS, unsafe_allow_html=True)

    for row_start in range(0, len(cards), columns):
        row = cards[row_start:row_start + columns]
        for column, card in zip(st.columns(columns, gap="large"), row):
            with column:
                _card(card, view_key, key_prefix)


def _card(card, view_key, key_prefix):
    dim = "" if card.enabled else " mode-soon"
    with st.container(border=True):
        st.markdown(
            f"<div class='mode-head{dim}'>"
            f"<span class='mode-badge' style='background:{card.accent};'>"
            f"{card.badge}</span>"
            f"<span class='mode-title'>{card.title}</span></div>"
            f"<div class='mode-blurb{dim}'>{card.blurb}</div>",
            unsafe_allow_html=True,
        )
        if card.enabled:
            if st.button(card.button, key=f"{key_prefix}_{card.view}",
                         type="primary", use_container_width=True):
                st.session_state[view_key] = card.view
                st.rerun()
        else:
            st.button("Not built yet", key=f"{key_prefix}_soon_{card.view}",
                      disabled=True, use_container_width=True,
                      help=card.soon_help or None)
