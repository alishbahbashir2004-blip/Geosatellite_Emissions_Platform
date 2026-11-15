# shared/charts.py
# The four figures every gas page draws: daily series, daily pixel
# availability, box plot, and distribution histogram. Gas naming/formatting
# comes in via ChartSpec; colour arrives pre-decided as `result["level_color"]`.

import altair as alt
import pandas as pd

from dataclasses import dataclass

CHART_HEIGHT = 340
CHART_HEIGHT_SHORT = 150
MUTED = "#6b7280"
HAIRLINE = "rgba(128,128,128,0.25)"

# Availability chart: valid pixels stand out, masked ones stay in the back.
VALID_COLOR = "#4c78a8"
NODATA_COLOR = "#c9ccd1"

# Distribution charts: middle 70% (P10-P80) keeps the level colour; tails are
# red, hot/cold in different reds (hot = candidate plume, cold = noise/terrain).
LOW_TAIL_COLOR = "#f0a3a3"
HIGH_TAIL_COLOR = "#d62728"
BG_BAND_COLOR = "#7f9cc0"  # neutral fill for the background chart's middle band
BAND_LABELS = ("Middle 70% (P10-P80)",
               "Below P10 (cold tail)",
               "Above P80 (hot tail)")


@dataclass(frozen=True)
class ChartSpec:
    """How one gas's numbers are named and printed on these charts.
    `digits`: tooltips/series line. `stat_digits`: box-plot/histogram labels."""
    value_key: str        # key in each `series` row: "ch4", "co", ...
    background_key: str   # result key holding the local background
    unit: str             # "ppb", "mmol/m²"
    axis_title: str       # "CH4 (ppb)" — the value axis on every figure
    digits: int           # tooltips and the series line
    stat_digits: int      # percentile labels on the box plot and histogram
    axis_format: str      # d3 tick format for the histogram's value axis
    series_pad: float     # minimum y padding on the series chart, in units
    box_pad: float        # minimum x padding on the box plot, in units


def _date_x():
    """Shared time axis, so the day-indexed charts line up day for day."""
    return alt.X("date:T", title=None,
                 axis=alt.Axis(format="%b %d", labelAngle=0, tickCount=6,
                               grid=False))


def _styled(chart):
    """Shared axis and view styling, so the figures read as one set."""
    return chart.configure_view(strokeWidth=0).configure_axis(
        labelColor=MUTED, titleColor=MUTED, tickColor=HAIRLINE,
        domainColor=HAIRLINE, gridColor="rgba(128,128,128,0.12)",
    )


def build_series_chart(result, spec):
    """Daily mean over the date range, with the local background as a rule,
    coloured by the gas's own level so the line matches the map highlight."""
    frame = pd.DataFrame(result["series"])
    frame["date"] = pd.to_datetime(frame["date"])
    color = result.get("level_color") or MUTED
    background = result.get(spec.background_key)
    key = spec.value_key

    # Domain is explicit, not zero-based — values sit far from zero and a zero
    # baseline would flatten the signal. Background is folded in so it stays on screen.
    values = list(frame[key]) + ([background] if background is not None else [])
    low, high = min(values), max(values)
    pad = max((high - low) * 0.15, spec.series_pad)
    y_scale = alt.Scale(domain=[low - pad, high + pad])
    y = alt.Y(f"{key}:Q", title=spec.axis_title, scale=y_scale)

    base = alt.Chart(frame).encode(x=_date_x())

    layers = [
        base.mark_area(color=color, opacity=0.12).encode(
            y=y, y2=alt.datum(low - pad)),
        base.mark_line(
            color=color, strokeWidth=2.5,
            point=alt.OverlayMarkDef(color=color, size=40, filled=True),
        ).encode(
            y=y,
            tooltip=[alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                     alt.Tooltip(f"{key}:Q", title=spec.axis_title,
                                 format=f".{spec.digits}f")],
        ),
    ]

    if background is not None:
        layers.insert(0, alt.Chart(
            pd.DataFrame({"background": [background]})
        ).mark_rule(color=MUTED, strokeDash=[5, 5]).encode(
            # First in the stack, so it carries the shared axis title.
            y=alt.Y("background:Q", title=spec.axis_title, scale=y_scale),
            tooltip=[alt.Tooltip("background:Q",
                                 title=f"Local background ({spec.unit})",
                                 format=f".{spec.digits}f")],
        ))

    return _styled(alt.layer(*layers).properties(height=CHART_HEIGHT))


def build_availability_chart(result):
    """Per-day pixel counts: valid retrievals vs. what masking removed.
    No ChartSpec needed — pixel counting is the same for every gas."""
    frame = pd.DataFrame(result["availability"])
    frame["date"] = pd.to_datetime(frame["date"])
    # Guarded so a day that sampled nothing shows an empty tooltip, not a NaN%.
    frame["coverage"] = (
        100 * frame["valid_count"]
        / frame["sample_count"].where(frame["sample_count"] > 0)
    )

    # Long form: one row per (day, category) is what a stacked bar wants.
    stacked = frame.melt(
        id_vars=["date", "sample_count", "coverage"],
        value_vars=["valid_count", "no_data_count"],
        var_name="kind", value_name="pixels",
    )
    stacked["kind"] = stacked["kind"].map({"valid_count": "Valid",
                                           "no_data_count": "Masked out"})

    bars = alt.Chart(stacked).mark_bar().encode(
        x=_date_x(),
        y=alt.Y("pixels:Q", title="Pixels in box"),
        color=alt.Color(
            "kind:N", title=None,
            scale=alt.Scale(domain=["Valid", "Masked out"],
                            range=[VALID_COLOR, NODATA_COLOR]),
            legend=alt.Legend(orient="top", labelColor=MUTED),
        ),
        # Descending puts "Valid" first, i.e. at the foot of each bar.
        order=alt.Order("kind:N", sort="descending"),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                 alt.Tooltip("kind:N", title="Pixels"),
                 alt.Tooltip("pixels:Q", title="Count", format=",.0f"),
                 alt.Tooltip("sample_count:Q", title="Sampled", format=",.0f"),
                 alt.Tooltip("coverage:Q", title="Valid share (%)",
                             format=".1f")],
    )

    # Valid share is usually too thin a sliver of the bar to read, so it also
    # runs as a line on its own right-hand axis.
    coverage = alt.Chart(frame).mark_line(
        color=VALID_COLOR, strokeWidth=2,
        point=alt.OverlayMarkDef(color=VALID_COLOR, size=35, filled=True),
    ).encode(
        x=_date_x(),
        y=alt.Y("coverage:Q", title="Valid share (%)",
                axis=alt.Axis(titleColor=VALID_COLOR, labelColor=VALID_COLOR)),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                 alt.Tooltip("coverage:Q", title="Valid share (%)",
                             format=".1f")],
    )

    chart = alt.layer(bars, coverage).resolve_scale(y="independent")
    return _styled(chart.properties(height=CHART_HEIGHT))


def build_box_plot(result, spec):
    """Horizontal box plot: box spans the quartiles, tick marks the median,
    whiskers reach P10/P80, faint rule behind is the full min-max range."""
    box = result["box_stats"]
    color = result.get("level_color") or MUTED
    frame = pd.DataFrame([box])

    # One shared scale, padded so the P10/P80 labels are not clipped.
    pad = max((box["max"] - box["min"]) * 0.04, spec.box_pad)
    scale = alt.Scale(domain=[box["min"] - pad, box["max"] + pad], nice=False)

    def x(field, title=None):
        return alt.X(f"{field}:Q", title=title, scale=scale)

    tooltip = [alt.Tooltip(f"{key}:Q", title=label, format=f".{spec.digits}f")
               for key, label in
               [("min", "Min"), ("p10", "P10"), ("p25", "P25"),
                ("p50", "Median"), ("p75", "P75"), ("p80", "P80"),
                ("max", "Max")]]

    base = alt.Chart(frame)
    layers = [
        # Full range first, so it sits behind the box.
        base.mark_rule(color=HAIRLINE, strokeWidth=1).encode(
            x=x("min", spec.axis_title), x2="max:Q"),
        base.mark_rule(color=color, strokeWidth=2, opacity=0.7).encode(
            x=x("p10"), x2="p80:Q"),
        base.mark_bar(color=color, opacity=0.3, height=30, stroke=color,
                      strokeWidth=1).encode(x=x("p25"), x2="p75:Q",
                                            tooltip=tooltip),
        base.mark_tick(color=color, thickness=3, size=38).encode(x=x("p50")),
    ]

    # P10/P80 lean outwards and the median sits a line higher, so a narrow
    # box doesn't pile all three labels on the same spot.
    def label(at, text, align, dy):
        return alt.Chart(pd.DataFrame([{"at": at, "text": text}])).mark_text(
            dy=dy, dx=6 if align == "left" else -6, align=align,
            fontSize=11, color=MUTED,
        ).encode(x=alt.X("at:Q", scale=scale, title=None), text="text:N")

    d = spec.stat_digits
    layers += [
        label(box["p10"], f"P10 {box['p10']:.{d}f}", "right", -26),
        label(box["p80"], f"P80 {box['p80']:.{d}f}", "left", -26),
        label(box["p50"], f"Median {box['p50']:.{d}f}", "center", -44),
    ]

    return _styled(alt.layer(*layers).properties(height=CHART_HEIGHT_SHORT))


def _tail_summary(frame, mask):
    """Pixel count, share and span of one tail, or None when it is empty."""
    total = float(frame["count"].sum())
    tail = frame[mask]
    count = float(tail["count"].sum())
    if not total or not count:
        return None
    return {"count": count, "pct": 100.0 * count / total,
            "lo": float(tail["start"].min()), "hi": float(tail["end"].max())}


def build_histogram_chart(result, spec):
    """The selected area's distribution."""
    return _distribution_chart(result["histogram"], result.get("box_stats"),
                               result.get("level_color") or MUTED, spec)


def build_bg_histogram_chart(result, spec):
    """The surrounding region's distribution, built by the same code as
    build_histogram_chart so the two are directly comparable."""
    return _distribution_chart(result["bg_histogram"],
                               result.get("bg_box_stats"), BG_BAND_COLOR, spec)


def _distribution_chart(rows, box, middle_color, spec):
    """Distribution of pixel values. Bars inside P10-P80 keep the level colour
    (matches the box plot); tails are red and labelled, since that's where a
    plume, bad retrieval, or clean air shows up."""
    frame = pd.DataFrame(rows)
    box = box or {}
    p10, p80 = box.get("p10"), box.get("p80")
    middle, low_label, high_label = BAND_LABELS
    d = spec.stat_digits

    total = float(frame["count"].sum())
    frame["share"] = 100.0 * frame["count"] / total if total else 0.0

    if p10 is None or p80 is None:
        frame["band"] = middle
    else:
        frame["band"] = [
            low_label if v < p10 else high_label if v > p80 else middle
            for v in frame["value"]
        ]

    bars = alt.Chart(frame).mark_bar().encode(
        # Bucket edges, so the bars meet without guessing a bar width.
        x=alt.X("start:Q", title=spec.axis_title,
                scale=alt.Scale(zero=False, nice=False),
                axis=alt.Axis(format=spec.axis_format, grid=False)),
        x2="end:Q",
        y=alt.Y("count:Q", title="Pixels"),
        y2=alt.datum(0),
        color=alt.Color(
            "band:N", title=None,
            scale=alt.Scale(domain=[middle, low_label, high_label],
                            range=[middle_color, LOW_TAIL_COLOR,
                                   HIGH_TAIL_COLOR]),
            legend=alt.Legend(orient="top", labelColor=MUTED),
        ),
        tooltip=[alt.Tooltip("value:Q", title=spec.axis_title,
                             format=f".{spec.digits}f"),
                 # Weighted: a part-masked cell counts as a fraction rather
                 # than rounding a visible bar down to "0".
                 alt.Tooltip("count:Q", title="Pixels (weighted)",
                             format=",.2f"),
                 alt.Tooltip("share:Q", title="Share of pixels (%)",
                             format=".2f"),
                 alt.Tooltip("band:N", title="Band")],
    )

    layers = [bars]

    if p10 is not None and p80 is not None:
        top = float(frame["count"].max())

        # Cut lines at P10/P80, matching the box plot's band.
        layers.append(
            alt.Chart(pd.DataFrame([{"at": p10}, {"at": p80}])).mark_rule(
                color=MUTED, strokeDash=[4, 4], strokeWidth=1,
            ).encode(x=alt.X("at:Q", title=None))
        )

        def annotation(at, lines, align, color, y_frac):
            """Tail figures written directly on the chart, not left to the tooltip."""
            return alt.Chart(
                pd.DataFrame([{"at": at, "text": "\n".join(lines)}])
            ).mark_text(
                align=align, dx=-6 if align == "right" else 6,
                fontSize=11, lineBreak="\n", color=color,
            ).encode(x=alt.X("at:Q", title=None), y=alt.datum(top * y_frac),
                     text="text:N")

        # Reach uses the reducer's own min/max (not bucket edge) to agree with the
        # Min/Max metrics; shares are bucket-counted, hence "~" (near, not exact).
        low = _tail_summary(frame, frame["value"] < p10)
        if low:
            layers.append(annotation(
                p10,
                [f"Below P10 ({p10:.{d}f} {spec.unit})",
                 f"{low['count']:,.1f} px  ~{low['pct']:.1f}%",
                 f"down to {box.get('min', low['lo']):.{d}f} {spec.unit}"],
                "right", HIGH_TAIL_COLOR, 0.92,
            ))

        high = _tail_summary(frame, frame["value"] > p80)
        if high:
            layers.append(annotation(
                p80,
                [f"Above P80 ({p80:.{d}f} {spec.unit})",
                 f"{high['count']:,.1f} px  ~{high['pct']:.1f}%",
                 f"up to {box.get('max', high['hi']):.{d}f} {spec.unit}"],
                "left", HIGH_TAIL_COLOR, 0.92,
            ))

    return _styled(alt.layer(*layers).properties(height=CHART_HEIGHT))
