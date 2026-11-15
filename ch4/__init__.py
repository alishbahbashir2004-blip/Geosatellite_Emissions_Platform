# ch4/
# The methane agent, and the anchor gas: what the other agents report is read
# as evidence for or against a source explanation for what shows up here.
#
# Self-contained, like every gas folder. config.py holds every CH4-specific
# decision, backend.py runs the pipeline, mapview.py and chartview.py say how
# methane's numbers are drawn.
#
# The page is split in three, because the agent now offers a choice of views:
#
#   frontend.py     what the router runs: sets the page config, then draws
#                   whichever view is picked. Owns the navigation chrome.
#   home.py         the landing cards — what would you like to do?
#   single_area.py  one area measured against its surroundings
#   compare.py      two areas of the same kind, read against each other
#                   (runs backend.run_area_pipeline — no background)
#
# A new view is a module with a render(), a card in home.py, and a line in
# frontend.py's VIEWS. Nothing else needs touching.
#
# This folder imports `shared` and nothing else of the app's. It imports
# nothing from any other gas, and no other gas imports anything from here.
