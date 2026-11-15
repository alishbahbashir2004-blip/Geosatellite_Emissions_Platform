# shared/ui.py
# Streamlit formatting helpers for every gas page; caller writes the unit in.

# Streamlit's delta arrow comes from a leading "-" in the delta string, so a
# "below background" line needs its arrow drawn by hand instead.
DELTA_GREEN = "#09ab3b"
DELTA_RED = "#ff2b2b"


def fmt(value, digits=2, signed=False):
    """Metric text: a fixed-width number, or a dash when missing. Signed for
    the "above background" figures, where the sign is the point."""
    if value is None:
        return "—"
    return f"{value:{'+' if signed else ''}.{digits}f}"


def fmt_range(low, high, digits=0):
    """Two stats shown as one span, e.g. the P10-P80 spread."""
    return "—" if low is None or high is None else f"{low:.{digits}f}–{high:.{digits}f}"


def fmt_pct(value, digits=1):
    """A percentage with its sign kept, or a dash."""
    return "—" if value is None else f"{value:+.{digits}f}%"


def level_delta(column, level, value):
    """Level line under an above-background metric: down/green when below
    background, up/red when above — follows the number's sign, not the label."""
    if not level:
        return
    below = value is not None and value < 0
    column.markdown(
        "<div style='color:{c};font-size:0.875rem;line-height:1.6;"
        "margin-top:-0.6rem;'>{a} {t}</div>".format(
            c=DELTA_GREEN if below else DELTA_RED,
            a="&#8595;" if below else "&#8593;", t=level),
        unsafe_allow_html=True,
    )


def note(text, color=None):
    """A one-line callout, optionally tinted by a level colour."""
    tint = color or "rgba(128,128,128,0.6)"
    return (
        f"<div style='font-size:0.85rem;line-height:1.5;border-left:3px solid "
        f"{tint};padding:0.35rem 0 0.35rem 0.7rem;opacity:0.9;'>{text}</div>"
    )
