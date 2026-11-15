# shared/
# Everything that is true for every gas, so no gas has to write it twice.
#
#   regions.py, cities.py  the named areas the location picker offers
#   geo.py                 name or coordinates -> bounding box; hotspot
#                          geometry arithmetic
#   earthengine.py         one-time EE session setup, and image -> map tiles
#   pipeline.py            daily means from a period's passes; segmenting the
#                          above-threshold pixels into contiguous patches
#   stats.py               EE reducer output -> chart rows
#   levels.py              the level-table convention and its colour key
#   charts.py              the four figures each gas page draws
#   mapview.py             the Folium map each gas page draws
#   chooser.py             the card grid a gas page opens on
#   ui.py                  Streamlit metric formatting
#   globeview.py           the spinning globe in the idle map slot
#
# Nothing in here knows a band name, a unit or a threshold. Those live in each
# gas's own folder, which is what keeps the gases independent of each other —
# a gas imports `shared`, never another gas.
#
# Where a shared figure still has to print a gas's numbers, the gas hands the
# naming in rather than this package guessing: ChartSpec in charts.py, MapSpec
# in mapview.py, and the `describe` callback in pipeline.py.
