# no2/
# The nitrogen dioxide agent. Self-contained: config.py holds every
# NO2-specific decision, backend.py runs the pipeline, mapview.py and
# chartview.py say how NO2's numbers are drawn, frontend.py is the page the
# router opens.
#
# Single-area only for now — no landing cards and no compare view, so
# frontend.py is the page itself rather than a dispatcher. Adding those later
# is the ch4/ split: move the page body into single_area.py, add home.py and
# compare.py, and turn frontend.py into the dispatcher.
#
# This folder imports `shared` and nothing else of the app's. It imports
# nothing from any other gas, and no other gas imports anything from here.
