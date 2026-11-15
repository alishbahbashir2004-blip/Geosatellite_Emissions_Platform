# shared/earthengine.py
# Earth Engine session setup + the image-to-tile-URL call, same for every gas.

import os

import ee

# Billed/quota'd project; override via EE_PROJECT.
EE_PROJECT = os.environ.get("EE_PROJECT", "gen-lang-client-0024514649")

# Set both for a deployed server (no interactive login available); a service
# account must be separately added to the project's Earth Engine access list.
# Unset locally: falls back to a cached `earthengine authenticate` login.
EE_SERVICE_ACCOUNT = os.environ.get("EE_SERVICE_ACCOUNT")
EE_SERVICE_ACCOUNT_KEY = os.environ.get("EE_SERVICE_ACCOUNT_KEY")

_initialised = False


def init():
    """Initialise Earth Engine once per process (Streamlit reruns the script
    but keeps the process, so this flag avoids re-initialising every touch)."""
    global _initialised
    if not _initialised:
        if EE_SERVICE_ACCOUNT and EE_SERVICE_ACCOUNT_KEY:
            credentials = ee.ServiceAccountCredentials(
                EE_SERVICE_ACCOUNT, EE_SERVICE_ACCOUNT_KEY)
            ee.Initialize(credentials, project=EE_PROJECT)
        else:
            ee.Initialize(project=EE_PROJECT)
        _initialised = True


def tile_url(image, vis_params):
    """An XYZ tile template ({x}/{y}/{z}) for an Earth Engine image."""
    map_id = image.getMapId(vis_params)
    fetcher = map_id.get("tile_fetcher")
    if fetcher is not None:
        return fetcher.url_format
    # Older earthengine-api versions expose the pieces directly.
    return ee.data.getTileUrl(map_id, "{x}", "{y}", "{z}")
