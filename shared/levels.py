# shared/levels.py
# The level-table convention every gas classifies against, plus its colour key.
# A level table is [(upper_bound, label, colour), ...] ordered by bound, last
# bound float("inf"); the unit is each gas's own business, this just walks it.

HAIRLINE = "rgba(128,128,128,0.25)"

UNKNOWN_LABEL = "Unknown"
UNKNOWN_COLOR = "#607d8b"


def classify(value, levels):
    """(label, colour) for `value` against a level table. A missing value
    classifies as unknown, not the lowest band — "couldn't measure" and
    "clean" are different findings and must not share a colour."""
    if value is None:
        return UNKNOWN_LABEL, UNKNOWN_COLOR
    for upper, label, color in levels:
        if value <= upper:
            return label, color
    return levels[-1][1], levels[-1][2]


def legend_html(levels, unit, title, digits=0):
    """Colour key for a level table, as an HTML block; bands are printed as
    the span between one bound and the next, not just a list of names."""
    gap = "" if unit == "%" else " "  # "%" wants no space before it, a unit does
    rows, lower = [], None
    for upper, label, color in levels:
        if upper == float("inf"):
            span = f"&gt; {lower:.{digits}f}"
        elif lower is None:
            span = f"&le; {upper:.{digits}f}"
        else:
            span = f"{lower:.{digits}f} to {upper:.{digits}f}"
        rows.append(
            '<div style="display:flex;align-items:center;gap:8px;padding:3px 0;">'
            f'<span style="width:12px;height:12px;border-radius:3px;flex:none;'
            f'background:{color};"></span><span style="flex:1;">{label}</span>'
            f'<span style="opacity:0.6;">{span}{gap}{unit}</span></div>'
        )
        lower = upper
    return (
        f'<div style="font-size:0.82rem;border:1px solid {HAIRLINE};'
        'border-radius:8px;padding:10px 14px;">'
        f'<div style="font-weight:600;padding-bottom:4px;">{title}</div>'
        + "".join(rows) + "</div>"
    )
