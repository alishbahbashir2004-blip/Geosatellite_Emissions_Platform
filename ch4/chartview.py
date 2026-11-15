# ch4/chartview.py
# Charts on the CH4 page. Figures are built by shared/charts.py; this file
# holds the ChartSpec (CH4's number formatting) and the emission-level colour key.

from shared.charts import (ChartSpec, build_availability_chart,
                           build_bg_histogram_chart as _bg_histogram,
                           build_box_plot as _box_plot,
                           build_histogram_chart as _histogram,
                           build_series_chart as _series)
from shared.levels import legend_html
from ch4.config import EMISSION_LEVELS, LEVEL_UNIT, LEVEL_TITLE, UNIT

__all__ = ["build_series_chart", "build_availability_chart", "build_box_plot",
           "build_histogram_chart", "build_bg_histogram_chart",
           "level_legend_html"]

SPEC = ChartSpec(
    value_key="ch4",
    background_key="background_ch4_ppb",
    unit=UNIT,
    axis_title=f"CH4 ({UNIT})",
    # CH4 runs near 1900 ppb with tens-of-ppb spread: 1 decimal for tooltips,
    # whole ppb for at-a-glance labels.
    digits=1,
    stat_digits=0,
    axis_format=".0f",
    series_pad=2.0,
    box_pad=1.0,
)


def build_series_chart(result):
    """Daily mean CH4 over the date range, with the background as a rule."""
    return _series(result, SPEC)


def build_box_plot(result):
    """Spread of CH4 across the pixels of the composite raster."""
    return _box_plot(result, SPEC)


def build_histogram_chart(result):
    """The selected area's CH4 distribution."""
    return _histogram(result, SPEC)


def build_bg_histogram_chart(result):
    """The surrounding region's CH4 distribution, drawn the same way."""
    return _bg_histogram(result, SPEC)


def level_legend_html():
    """Colour key for the emission levels, in ppb above local background."""
    return legend_html(EMISSION_LEVELS, LEVEL_UNIT, LEVEL_TITLE, digits=0)
