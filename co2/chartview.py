# co2/chartview.py
# CO2's own figures — not shared/charts.py, since these charts (decomposition,
# inferred range, coverage timeline) don't share that module's shape.

import altair as alt
import pandas as pd

from co2.config import (ACCENT, SEASON_UP_COLOR, SEASON_DOWN_COLOR,
                        EMISSION_RATIOS)

CHART_HEIGHT = 300
CHART_HEIGHT_SHORT = 160
MUTED = "#6b7280"
HAIRLINE = "rgba(128,128,128,0.25)"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _styled(chart):
    return chart.configure_view(strokeWidth=0).configure_axis(
        labelColor=MUTED, titleColor=MUTED, tickColor=HAIRLINE,
        domainColor=HAIRLINE, gridColor="rgba(128,128,128,0.12)",
    )


def _hover(frame, tooltips):
    """A nearest-day hover target spanning the full chart height. Must use
    `encodings=["x"]`, not `fields=["date"]`, to match screen position not
    value; other layers need `tooltip=alt.value(None)` or hover breaks."""
    nearest = alt.selection_point(nearest=True, on="mouseover",
                                  encodings=["x"], empty=False)
    return alt.Chart(frame).mark_rule(
        color=MUTED, strokeWidth=1, opacity=0).encode(
        x=alt.X("date:T", title=None),
        opacity=alt.condition(nearest, alt.value(0.45), alt.value(0)),
        tooltip=tooltips,
    ).add_params(nearest)


def _frame(result):
    frame = pd.DataFrame({
        "date": pd.to_datetime(result["dates"]),
        "value": result["values"],
        "trend": result["trend"],
        "seasonal": result["seasonal"],
        "remainder": result["remainder"],
        "deseasonalised": result["deseasonalised"],
    })
    # value vs. trend at the same date; tooltip states both plus this gap.
    frame["gap"] = frame["value"] - frame["trend"]
    return frame


# ---------------------------------------------------------------------------
# Coverage — which products exist, and when
# ---------------------------------------------------------------------------

def build_coverage_chart(rows, date_start, date_end):
    """A bar per product showing its window against the requested one."""
    frame = pd.DataFrame([{
        "label": row["label"],
        "start": pd.to_datetime(row["start"]),
        "end": pd.to_datetime(row["end"]),
        "kind": row["kind"].title(),
        "covers": "Covers your dates" if row["covers_request"]
                  else "No data for your dates",
    } for row in rows])

    bars = alt.Chart(frame).mark_bar(height=16, cornerRadius=3).encode(
        x=alt.X("start:T", title=None,
                scale=alt.Scale(nice=False),
                axis=alt.Axis(format="%Y", tickCount=8, grid=False)),
        x2="end:T",
        y=alt.Y("label:N", title=None, sort=None,
                axis=alt.Axis(labelLimit=260)),
        color=alt.Color("covers:N", title=None,
                        scale=alt.Scale(
                            domain=["Covers your dates",
                                    "No data for your dates"],
                            range=[ACCENT, "#c9ccd1"]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("label:N", title="Product"),
                 alt.Tooltip("kind:N", title="Kind"),
                 alt.Tooltip("start:T", title="From", format="%Y-%m-%d"),
                 alt.Tooltip("end:T", title="To", format="%Y-%m-%d")],
    )

    window = pd.DataFrame({"start": [pd.to_datetime(date_start)],
                           "end": [pd.to_datetime(date_end)]})
    requested = alt.Chart(window).mark_rect(
        color="#c62828", opacity=0.12).encode(
        x="start:T", x2="end:T", tooltip=alt.value(None))
    edges = alt.Chart(window).transform_fold(
        ["start", "end"], as_=["edge", "when"]).mark_rule(
        color="#c62828", strokeDash=[4, 3], size=1.2).encode(x="when:T")

    return _styled((requested + edges + bars).properties(
        height=len(frame) * 34 + 30).resolve_scale(color="independent"))


# ---------------------------------------------------------------------------
# Trend and seasonal cycle
# ---------------------------------------------------------------------------

def build_record_chart(result, date_start=None, date_end=None):
    """The whole XCO2 record for the area, with the fitted trend on top."""
    frame = _frame(result)
    values = frame["value"]
    pad = max((values.max() - values.min()) * 0.06, 0.5)

    base = alt.Chart(frame).encode(
        x=alt.X("date:T", title=None,
                axis=alt.Axis(format="%Y", tickCount=8, grid=False)))
    # Hover layer below owns the tooltip for the whole chart.
    line = base.mark_line(color=ACCENT, strokeWidth=1.1).encode(
        y=alt.Y("value:Q", title="XCO2 (ppm)",
                scale=alt.Scale(domain=[values.min() - pad,
                                        values.max() + pad], nice=False)),
        tooltip=alt.value(None))
    trend = base.mark_line(color="#c62828", strokeDash=[5, 4],
                           strokeWidth=1.5).encode(
        y="trend:Q", tooltip=alt.value(None))

    layers = [line, trend, _hover(frame, [
        alt.Tooltip("date:T", title="Date", format="%Y-%m-%d"),
        alt.Tooltip("value:Q", title="Measured XCO2 (ppm)", format=".2f"),
        alt.Tooltip("trend:Q", title="Trend line (ppm)", format=".2f"),
        alt.Tooltip("gap:Q", title="Measured − trend", format="+.2f"),
        alt.Tooltip("seasonal:Q", title="Seasonal offset", format="+.2f"),
        alt.Tooltip("remainder:Q", title="Left over", format="+.2f"),
    ])]
    if date_start and date_end:
        window = pd.DataFrame({"start": [pd.to_datetime(date_start)],
                               "end": [pd.to_datetime(date_end)]})
        layers.insert(0, alt.Chart(window).mark_rect(
            color="#1f77b4", opacity=0.10).encode(
            x="start:T", x2="end:T", tooltip=alt.value(None)))

    return _styled(alt.layer(*layers).properties(height=CHART_HEIGHT))


def build_seasonal_chart(result):
    """The yearly cycle on its own, coloured by what's physically happening
    (uptake vs. release) rather than by high/low."""
    profile = result.get("seasonal_profile")
    if not profile:
        return None
    frame = pd.DataFrame({
        "month": MONTHS, "order": range(1, 13), "value": profile,
        "phase": ["Land releasing CO2" if value > 0 else "Land absorbing CO2"
                  for value in profile]})

    bars = alt.Chart(frame).mark_bar(cornerRadius=2).encode(
        x=alt.X("month:N", title=None, sort=MONTHS,
                axis=alt.Axis(labelAngle=0, grid=False)),
        y=alt.Y("value:Q", title="ppm above / below the year's mean"),
        color=alt.Color("phase:N", title=None,
                        scale=alt.Scale(
                            domain=["Land releasing CO2",
                                    "Land absorbing CO2"],
                            range=[SEASON_UP_COLOR, SEASON_DOWN_COLOR]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("month:N", title="Month"),
                 alt.Tooltip("value:Q", title="ppm", format="+.2f"),
                 alt.Tooltip("phase:N", title="")])
    zero = alt.Chart(frame).mark_rule(color=MUTED, size=0.8).encode(
        y=alt.datum(0))
    return _styled((bars + zero).properties(height=CHART_HEIGHT_SHORT + 40))


def build_remainder_chart(result):
    """What is left once the rise and yearly cycle are removed — shown
    against its own std dev, since this is where signal and noise both live."""
    frame = _frame(result)
    spread = result["remainder_std"]
    band = pd.DataFrame({"low": [-spread], "high": [spread]})

    # tooltip=alt.value(None): full-plot marks would otherwise swallow hover.
    shading = alt.Chart(band).mark_rect(color=MUTED, opacity=0.13).encode(
        y="low:Q", y2="high:Q", tooltip=alt.value(None))
    line = alt.Chart(frame).mark_line(color=ACCENT, strokeWidth=0.9).encode(
        x=alt.X("date:T", title=None,
                axis=alt.Axis(format="%Y", tickCount=8, grid=False)),
        y=alt.Y("remainder:Q", title="ppm left over"),
        tooltip=alt.value(None))
    zero = alt.Chart(frame).mark_rule(color=MUTED, size=0.8).encode(
        y=alt.datum(0), tooltip=alt.value(None))
    hover = _hover(frame, [
        alt.Tooltip("date:T", title="Date", format="%Y-%m-%d"),
        alt.Tooltip("remainder:Q", title="Left over (ppm)", format="+.2f"),
        alt.Tooltip("value:Q", title="Measured (ppm)", format=".2f"),
        alt.Tooltip("trend:Q", title="Trend (ppm)", format=".2f"),
        alt.Tooltip("seasonal:Q", title="Seasonal offset", format="+.2f"),
    ])
    return _styled((shading + zero + line + hover).properties(
        height=CHART_HEIGHT_SHORT))


# ---------------------------------------------------------------------------
# Anomaly against the surrounding box
# ---------------------------------------------------------------------------

def build_anomaly_chart(result):
    """AOI minus surroundings, both detrended/deseasonalised first. The grey
    band is the scatter; a line inside it means the boxes are indistinguishable."""
    frame = pd.DataFrame({"date": pd.to_datetime(result["dates"]),
                          "anomaly": result["anomaly"]})
    noise = result["anomaly_noise"]
    band = pd.DataFrame({"low": [-noise], "high": [noise]})

    shading = alt.Chart(band).mark_rect(color=MUTED, opacity=0.13).encode(
        y="low:Q", y2="high:Q", tooltip=alt.value(None))
    line = alt.Chart(frame).mark_line(
        color=result.get("level_color") or ACCENT, strokeWidth=1.0).encode(
        x=alt.X("date:T", title=None,
                axis=alt.Axis(format="%Y", tickCount=8, grid=False)),
        y=alt.Y("anomaly:Q", title="Area minus surroundings (ppm)"),
        tooltip=alt.value(None))
    mean = alt.Chart(pd.DataFrame({"y": [result["mean_anomaly"]]})).mark_rule(
        color="#c62828", strokeDash=[5, 4], size=1.4).encode(
        y="y:Q", tooltip=alt.value(None))
    zero = alt.Chart(frame).mark_rule(color=MUTED, size=0.8).encode(
        y=alt.datum(0), tooltip=alt.value(None))
    hover = _hover(frame, [
        alt.Tooltip("date:T", title="Date", format="%Y-%m-%d"),
        alt.Tooltip("anomaly:Q", title="Area − surroundings (ppm)",
                    format="+.3f"),
    ])
    return _styled((shading + zero + line + mean + hover).properties(
        height=CHART_HEIGHT))


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def build_inventory_chart(result):
    """Monthly fossil-fuel CO2 intensity across the requested window."""
    frame = pd.DataFrame([{
        "date": pd.to_datetime(row["date"]),
        "value": row["mean_tco2_per_km2_month"],
        "total": row["total_mtco2_per_year"],
    } for row in result["monthly"]])

    bars = alt.Chart(frame).mark_bar(color=ACCENT, cornerRadius=2).encode(
        x=alt.X("date:T", title=None,
                axis=alt.Axis(format="%b %Y", labelAngle=-40, grid=False)),
        y=alt.Y("value:Q", title="tonnes CO2 per km² per month"),
        tooltip=[alt.Tooltip("date:T", title="Month", format="%B %Y"),
                 alt.Tooltip("value:Q", title="t CO2 / km² / month",
                             format=",.1f"),
                 alt.Tooltip("total:Q", title="Implied Mt CO2 / year",
                             format=",.2f")])
    return _styled(bars.properties(height=CHART_HEIGHT))


# ---------------------------------------------------------------------------
# Targeted snapshot
# ---------------------------------------------------------------------------

def build_snapshot_histogram(result):
    """The distribution of one snapshot's soundings."""
    histogram = (result.get("stats") or {}).get("histogram")
    if not histogram or len(histogram) != 2:
        return None
    counts, edges = histogram
    frame = pd.DataFrame({
        "low": edges[:-1], "high": edges[1:], "count": counts})

    bars = alt.Chart(frame).mark_bar(color=ACCENT).encode(
        x=alt.X("low:Q", title="XCO2 (ppm)",
                scale=alt.Scale(domain=[edges[0], edges[-1]], nice=False),
                axis=alt.Axis(format=".1f", grid=False)),
        x2="high:Q",
        y=alt.Y("count:Q", title="grid cells"),
        tooltip=[alt.Tooltip("low:Q", title="From (ppm)", format=".2f"),
                 alt.Tooltip("high:Q", title="To (ppm)", format=".2f"),
                 alt.Tooltip("count:Q", title="Cells", format=",.0f")])
    mean = alt.Chart(
        pd.DataFrame({"x": [result["stats"]["mean"]]})).mark_rule(
        color="#c62828", strokeDash=[5, 4], size=1.4).encode(x="x:Q")
    return _styled((bars + mean).properties(height=CHART_HEIGHT))


def build_snapshot_timeline(result):
    """Every targeted snapshot ever taken over this area, as a strip of
    dates — opportunistic captures, not a time series; the gaps are the point."""
    items = result.get("all_items") or []
    if not items:
        return None
    window_start, window_end = result["requested"]
    frame = pd.DataFrame([{
        "date": pd.to_datetime(item["date"]),
        "id": item["id"],
        "state": ("In your window"
                  if window_start <= item["date"] <= window_end
                  else "Outside your window"),
    } for item in items])

    ticks = alt.Chart(frame).mark_tick(thickness=2.5, size=26).encode(
        x=alt.X("date:T", title=None,
                axis=alt.Axis(format="%b %Y", labelAngle=-40, grid=False)),
        color=alt.Color("state:N", title=None,
                        scale=alt.Scale(domain=["In your window",
                                                "Outside your window"],
                                        range=[ACCENT, "#c9ccd1"]),
                        legend=alt.Legend(orient="bottom")),
        tooltip=[alt.Tooltip("date:T", title="Snapshot", format="%Y-%m-%d"),
                 alt.Tooltip("id:N", title="Item")])
    return _styled(ticks.properties(height=70))


# ---------------------------------------------------------------------------
# Inferred from NO2
# ---------------------------------------------------------------------------

def build_inferred_chart(result, measured_ppm=None):
    """The inferred CO2 range, as a range not a number — three bars since the
    emission ratio is uncertain by several times. A measured enhancement,
    where one exists, is drawn alongside for comparison."""
    inferred = result.get("inferred")
    if not inferred:
        return None
    frame = pd.DataFrame([
        {"case": f"NOx-rich\n({EMISSION_RATIOS['low']:.0f}:1)",
         "order": 0, "value": inferred["low"]},
        {"case": f"Mixed urban\n({EMISSION_RATIOS['central']:.0f}:1)",
         "order": 1, "value": inferred["central"]},
        {"case": f"NOx-controlled\n({EMISSION_RATIOS['high']:.0f}:1)",
         "order": 2, "value": inferred["high"]},
    ])
    bars = alt.Chart(frame).mark_bar(color=ACCENT, cornerRadius=2,
                                     size=48).encode(
        x=alt.X("case:N", title="assumed CO2 : NOx emission ratio", sort=None,
                axis=alt.Axis(labelAngle=0, grid=False)),
        y=alt.Y("value:Q", title="implied CO2 enhancement (ppm)"),
        tooltip=[alt.Tooltip("case:N", title="Assumption"),
                 alt.Tooltip("value:Q", title="ppm", format=".3f")])
    labels = bars.mark_text(dy=-8, color=MUTED, fontSize=11).encode(
        text=alt.Text("value:Q", format=".3f"))

    layers = [bars, labels]
    if measured_ppm is not None:
        rule = alt.Chart(
            pd.DataFrame({"y": [measured_ppm]})).mark_rule(
            color="#c62828", strokeDash=[5, 4], size=1.4).encode(y="y:Q")
        layers.append(rule)
    return _styled(alt.layer(*layers).properties(height=CHART_HEIGHT))
