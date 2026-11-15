# api/encode.py
# Guard between numpy and JSON: numpy scalars (np.bool_, np.int64, ...) don't
# all serialise like the Python types they resemble. Walks the response once
# so a value that slips through analysis-code casts is converted, not a 500.

import math

import numpy as np


def jsonable(value):
    """A response with every numpy scalar and array turned into a native."""
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [jsonable(item) for item in value.tolist()]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float):
        # JSON has no NaN/Infinity tokens — send missing numbers as null.
        return None if math.isnan(value) or math.isinf(value) else value
    return value
