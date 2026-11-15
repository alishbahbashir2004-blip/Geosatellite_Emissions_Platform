# shared/stats.py
# Reshapes EE reducer output for the charts. Unit-agnostic: caller labels
# the axis, this only moves numbers around.

import math


def histogram_rows(hist):
    """EE histogram output -> one chart row per bucket, with each row's span
    (not just its centre) rebuilt by snapping bucketMeans to bucketWidth,
    since EE's buckets align to multiples of it."""
    if not hist:
        return None
    means = hist.get("bucketMeans") or []
    counts = hist.get("histogram") or []
    width = hist.get("bucketWidth") or 0
    if not width:
        return [{"value": m, "start": m, "end": m, "count": c}
                for m, c in zip(means, counts)]
    rows = []
    for m, c in zip(means, counts):
        start = math.floor(m / width) * width
        rows.append({"value": m, "start": start, "end": start + width,
                     "count": c})
    return rows


def box_stats(rows, quantiles):
    """Box-plot summary of the same pixels the histogram counts; None when the
    histogram is empty or any cut is missing, so the caller can skip the plot."""
    if not rows or any(v is None for v in quantiles.values()):
        return None
    return dict(quantiles)


def feature_stat(props, name):
    """Pull one reduceToVectors output, whether or not it is band-prefixed."""
    if name in props:
        return props[name]
    for key, value in props.items():
        if key.endswith(f"_{name}"):
            return value
    return None
