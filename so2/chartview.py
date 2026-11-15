# so2/chartview.py
# Charts on the SO2 page; shared/charts.py draws them identically for every gas.
# Here: the ChartSpec (labels, precision) and the emission-level colour key.

from shared.charts import (ChartSpec, build_availability_chart,
                           build_bg_histogram_chart as _bg_histogram,
                           build_box_plot as _box_plot,
                           build_histogram_chart as _histogram,
                           build_series_chart as _series)
from shared.levels import legend_html
from so2.config import EMISSION_LEVELS, LEVEL_UNIT, LEVEL_TITLE, UNIT

__all__ = ["build_series_chart", "build_availability_chart", "build_box_plot",
           "build_histogram_chart", "build_bg_histogram_chart",
           "level_legend_html"]

SPEC = ChartSpec(
    value_key="so2",
    background_key="background_so2",
    unit=UNIT,
    axis_title=f"SO2 ({UNIT})",
    # One decimal carries the signal in a tooltip; whole units suffice for a
    # label read at a glance.
    digits=1,
    stat_digits=0,
    axis_format=".0f",
    series_pad=2.0,
    box_pad=1.0,
)


def build_series_chart(result):
    """Daily mean SO2 over the date range, with the background as a rule."""
    return _series(result, SPEC)


def build_box_plot(result):
    """Spread of SO2 across the pixels of the composite raster."""
    return _box_plot(result, SPEC)


def build_histogram_chart(result):
    """The selected area's SO2 distribution."""
    return _histogram(result, SPEC)


def build_bg_histogram_chart(result):
    """The surrounding region's SO2 distribution, drawn the same way."""
    return _bg_histogram(result, SPEC)


def level_legend_html():
    """Colour key for the enhancement levels."""
    return legend_html(EMISSION_LEVELS, LEVEL_UNIT, LEVEL_TITLE, digits=0)
