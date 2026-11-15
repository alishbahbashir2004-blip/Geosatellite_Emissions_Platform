# gas_registry.py
# The one place a gas is declared. dashboard.py and app.py both build off
# this list, so adding a gas means writing its folder and an entry here —
# no edits to the dashboard or router. `page=None` marks a declared-but-
# unbuilt gas (greyed out on the dashboard, not routable).

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Gas:
    key: str                  # short id, also the URL path segment
    formula: str              # "CH4" — shown in the card badge
    name: str                 # "Methane"
    page: Optional[str]       # entry script, or None while unbuilt
    icon: str                 # emoji, shown in the router's sidebar
    accent: str               # hex, the card's badge and rule colour
    product: str              # which satellite product it comes from
    unit: str                 # the unit its headline number is reported in
    since: str                # first date the product has data for
    sdgs: tuple = field(default_factory=tuple)
    # Not drawn on the dashboard card; source text for the report generator.
    tells_you: str = ""       # one line: what this gas answers on its own
    in_combination: str = ""  # one line: what it adds next to the others


# Order here is the order the dashboard draws the cards in: built gases
# first, then the ones still to come.
GASES = (
    Gas(
        key="ch4",
        formula="CH4",
        name="Methane",
        page="ch4/frontend.py",
        icon=":material/local_fire_department:",
        accent="#d32f2f",
        product="Sentinel-5P TROPOMI · OFFL L3 CH4",
        unit="ppb (column mixing ratio)",
        since="2018-11-28",
        tells_you="Where methane sits above its local background — leaks, "
                  "venting, and unlit flares.",
        in_combination="The anchor gas. Everything else is read as evidence "
                       "for or against a source explanation for CH4.",
        sdgs=("SDG 13",),
    ),
    Gas(
        key="co",
        formula="CO",
        name="Carbon monoxide",
        page="co/frontend.py",
        icon=":material/mode_heat:",
        accent="#e07b39",
        product="Sentinel-5P TROPOMI · OFFL L3 CO",
        unit="mmol/m² (total column)",
        since="2018-07-04",
        tells_you="Where incomplete combustion is happening — flaring, "
                  "engines, biomass burning.",
        in_combination="CH4 high <b>and</b> CO high points at combustion. "
                       "CH4 high with CO flat points at a fugitive leak "
                       "instead.",
        sdgs=("SDG 3", "SDG 13"),
    ),
    Gas(
        key="no2",
        formula="NO2",
        name="Nitrogen dioxide",
        page="no2/frontend.py",
        icon=":material/factory:",
        accent="#8e6bbf",
        product="Sentinel-5P TROPOMI · OFFL L3 NO2",
        unit="µmol/m² (tropospheric column)",
        since="2018-06-28",
        tells_you="Where high-temperature combustion and traffic are — a "
                  "short-lived tracer, so it stays near its source.",
        in_combination="Separates industrial and traffic combustion from "
                       "biomass burning, which is CO-rich but NO2-poor.",
        sdgs=("SDG 3", "SDG 11"),
    ),
    Gas(
        key="co2",
        formula="CO2",
        name="Carbon dioxide",
        page="co2/frontend.py",
        icon=":material/co2:",
        accent="#2e7d32",
        product="OCO-2/3 XCO2 + ODIAC inventory (NASA GHG Center)",
        unit="ppm (column mixing ratio)",
        since="2015-01-01",
        tells_you="How CO2 over an area is rising and how hard its "
                  "vegetation breathes — and where the emissions come from.",
        in_combination="The one gas whose own signal is too small to see at "
                       "city scale, so it is inferred from NO2 instead: CH4 "
                       "and CO say what is leaking or burning, NO2 says how "
                       "much CO2 that burning implies.",
        sdgs=("SDG 7", "SDG 13"),
    ),
    Gas(
        key="so2",
        formula="SO2",
        name="Sulphur dioxide",
        page="so2/frontend.py",
        icon=":material/oil_barrel:",
        accent="#4b8b9b",
        product="Sentinel-5P TROPOMI · OFFL L3 SO2",
        unit="µmol/m² (column)",
        since="2018-07-10",
        tells_you="Where sour gas is processed or burned, and where volcanoes "
                  "are degassing.",
        in_combination="Marks sour-gas and refinery sources specifically, "
                       "which CO alone cannot tell from a clean flare.",
        sdgs=("SDG 3",),
    ),
)

GASES_BY_KEY = {gas.key: gas for gas in GASES}


def live_gases():
    """The gases that have a page behind them."""
    return tuple(gas for gas in GASES if gas.page)


def planned_gases():
    """Declared but not built yet — listed on the dashboard, not routable."""
    return tuple(gas for gas in GASES if not gas.page)
