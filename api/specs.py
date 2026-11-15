# api/specs.py
# Flattens each gas's config/chartview/mapview modules into one JSON-able
# descriptor for the React client. CO2 isn't included: it has five analyses
# and no single result, and is routed separately in api/main.py.

import importlib
from dataclasses import dataclass

from gas_registry import GASES, GASES_BY_KEY


@dataclass(frozen=True)
class GasSpec:
    """Where a gas's numbers live in its result dict, and how to print them.

    `stat_suffix`: methane's keys are `mean_ch4_ppb`/`enhancement_ppb`; the
    other three use the bare formula (`mean_co`, `enhancement_no2`).
    """
    key: str
    stat_suffix: str          # mean_<suffix>, min_<suffix>, p10_<suffix>, ...
    enhancement_key: str      # the absolute enhancement
    headline_pct: bool        # is the headline a percent or an absolute?
    has_compare: bool


SPECS = {
    "ch4": GasSpec("ch4", "ch4_ppb", "enhancement_ppb", False, True),
    "co": GasSpec("co", "co", "enhancement_co", True, True),
    "no2": GasSpec("no2", "no2", "enhancement_no2", True, False),
    "so2": GasSpec("so2", "so2", "enhancement_so2", False, False),
}

S5P_KEYS = tuple(SPECS)


def modules(key):
    """A gas's backend, chartview, mapview and config.

    Never imports `<gas>.frontend`: it calls st.set_page_config() at import
    time and would drag Streamlit into the API process.
    """
    return {name: importlib.import_module(f"{key}.{name}")
            for name in ("backend", "chartview", "mapview", "config")}


def descriptor(key):
    """Everything the client needs to render one gas's page, as JSON."""
    spec = SPECS[key]
    gas = GASES_BY_KEY[key]
    parts = modules(key)
    config, chartview, mapview = parts["config"], parts["chartview"], parts["mapview"]

    return {
        "key": key,
        "formula": gas.formula,
        "name": gas.name,
        "accent": gas.accent,
        "product": gas.product,
        "unit": config.UNIT,
        "coverageStart": config.COVERAGE_START,
        "defaultHotspots": config.DEFAULT_HOTSPOT_REGIONS,
        "statSuffix": spec.stat_suffix,
        "enhancementKey": spec.enhancement_key,
        "headlinePct": spec.headline_pct,
        "hasCompare": spec.has_compare,
        "digits": chartview.SPEC.digits,
        "statDigits": chartview.SPEC.stat_digits,
        "axisTitle": chartview.SPEC.axis_title,
        "palette": list(mapview.SPEC.palette),
        "hotspotColor": mapview.SPEC.hotspot_color,
        "colorbarCaption": mapview.SPEC.colorbar_caption,
        "levels": [
            {"upper": None if upper == float("inf") else upper,
             "label": label, "color": color}
            for upper, label, color in config.EMISSION_LEVELS
        ],
        "levelUnit": config.LEVEL_UNIT,
        "levelTitle": config.LEVEL_TITLE,
        "noiseNote": getattr(config, "NOISE_NOTE", None),
    }


def dashboard():
    """The registry as the dashboard's cards, built and unbuilt alike."""
    return [{
        "key": gas.key, "formula": gas.formula, "name": gas.name,
        "accent": gas.accent, "product": gas.product, "unit": gas.unit,
        "since": gas.since, "sdgs": list(gas.sdgs),
        "tellsYou": gas.tells_you, "inCombination": gas.in_combination,
        "live": gas.page is not None,
    } for gas in GASES]
