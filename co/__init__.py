# co/
# The carbon monoxide agent. Self-contained: config.py holds every CO-specific
# decision, backend.py runs the pipelines, mapview.py and chartview.py say how
# CO's numbers are drawn.
#
# The page is split in three, the same way ch4/ is, because the agent offers a
# choice of views:
#
#   frontend.py     what the router runs: sets the page config, then draws
#                   whichever view is picked. Owns the navigation chrome.
#   home.py         the landing cards — what would you like to do?
#   single_area.py  one area measured against its surroundings
#   compare.py      two areas of the same kind, read against each other
#                   (runs backend.run_area_pipeline — no background)
#
# This folder imports `shared` and nothing else of the app's. It imports
# nothing from any other gas, and no other gas imports anything from here —
# the one exception is a navigation link to the methane page, which is a page
# path rather than an import.
