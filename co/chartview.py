# co/chartview.py
# Charts on the CO page. Figures are built by shared/charts.py; this file
# holds the ChartSpec and two legends — CO reports both enhancement and loading.

from shared.charts import (ChartSpec, build_availability_chart,
                           build_bg_histogram_chart as _bg_histogram,
                           build_box_plot as _box_plot,
                           build_histogram_chart as _histogram,
                           build_series_chart as _series)
from shared.levels import legend_html
from co.config import (EMISSION_LEVELS, LEVEL_UNIT, LEVEL_TITLE,
                       REGIONAL_LOADING_LEVELS, LOADING_UNIT, LOADING_TITLE,
                       UNIT)

__all__ = ["build_series_chart", "build_availability_chart", "build_box_plot",
           "build_histogram_chart", "build_bg_histogram_chart",
           "level_legend_html", "loading_legend_html"]

SPEC = ChartSpec(
    value_key="co",
    background_key="background_co",
    unit=UNIT,
    axis_title=f"CO ({UNIT})",
    # CO sits near 27 mmol/m2 with ~unit day-to-day spread, so 2 decimals are
    # needed everywhere (unlike CH4's whole-ppb precision).
    digits=2,
    stat_digits=2,
    axis_format=".1f",
    series_pad=0.5,
    box_pad=0.05,
)


def build_series_chart(result):
    """Daily mean CO over the date range, with the background as a rule. Days
    with no usable pixel are missing — see the availability chart."""
    return _series(result, SPEC)


def build_box_plot(result):
    """Spread of the CO column across the pixels of the composite raster."""
    return _box_plot(result, SPEC)


def build_histogram_chart(result):
    """The selected area's CO distribution."""
    return _histogram(result, SPEC)


def build_bg_histogram_chart(result):
    """The surrounding region's CO distribution, drawn the same way."""
    return _bg_histogram(result, SPEC)


def level_legend_html():
    """Colour key for the enhancement levels, in percent of local background."""
    return legend_html(EMISSION_LEVELS, LEVEL_UNIT, LEVEL_TITLE, digits=0)


def loading_legend_html():
    """Colour key for the regional-loading bands (absolute column units).
    Separate from level_legend_html: that one says if the area stands out
    from its surroundings; this one says if the surroundings were clean."""
    return legend_html(REGIONAL_LOADING_LEVELS, LOADING_UNIT, LOADING_TITLE,
                       digits=0)
