# co2/analysis.py
# CO2-specific maths with no counterpart in the other gases: adequacy(),
# decompose(), and infer_from_no2().

from datetime import date

import numpy as np

from co2.config import (SOURCES, MIN_CELLS_FOR_READING, MIN_CELLS_FOR_PATTERN,
                        MIN_YEARS_FOR_TREND, MIN_YEARS_FOR_SEASONAL,
                        EMISSION_RATIOS, DRY_AIR_COLUMN_MOL_M2,
                        ANOMALY_LEVELS, CARBON_TO_CO2)


# ---------------------------------------------------------------------------
# Can this question be answered?
# ---------------------------------------------------------------------------

def adequacy(bbox, source_key):
    """How many of a product's cells the AOI spans; returns cells/cell_km/
    verdict/suggestion for the page to render directly."""
    source = SOURCES[source_key]
    cell_lat, cell_lon = source["cell_deg"]
    span_lat = abs(bbox["N"] - bbox["S"])
    span_lon = abs(bbox["E"] - bbox["W"])

    cells_lat = span_lat / cell_lat
    cells_lon = span_lon / cell_lon
    cells = cells_lat * cells_lon

    mid_lat = (bbox["N"] + bbox["S"]) / 2.0
    km_lat = cell_lat * 111.0
    km_lon = cell_lon * 111.0 * max(np.cos(np.radians(mid_lat)), 0.01)

    if cells < MIN_CELLS_FOR_READING:
        verdict = "too_small"
    elif cells < MIN_CELLS_FOR_PATTERN:
        verdict = "value_only"
    else:
        verdict = "ok"

    # Side length of the smallest box holding a 2x2 block of cells.
    need_lat = cell_lat * 2
    need_lon = cell_lon * 2
    return {
        "source": source_key,
        "label": source["label"],
        "cells_lat": cells_lat, "cells_lon": cells_lon, "cells": cells,
        "cell_deg": (cell_lat, cell_lon),
        "cell_km": (km_lat, km_lon),
        "span_deg": (span_lat, span_lon),
        "verdict": verdict,
        "need_deg": (need_lat, need_lon),
        "suggestion": _suggestion(verdict, source, need_lat, need_lon,
                                  km_lat, km_lon),
    }


def _suggestion(verdict, source, need_lat, need_lon, km_lat, km_lon):
    if verdict == "ok":
        return None
    if verdict == "value_only":
        return (f"Big enough for a single value, not for a spatial pattern. "
                f"One {source['label']} cell is about "
                f"{km_lat:.0f} x {km_lon:.0f} km here, so the map would show "
                f"a handful of blocks rather than structure.")
    return (f"One {source['label']} cell is about {km_lat:.0f} x {km_lon:.0f} "
            f"km at this latitude. To get even a 2x2 block of real cells the "
            f"area needs to be at least {need_lat:.2f}° tall and "
            f"{need_lon:.2f}° wide — roughly {2 * km_lat:.0f} x "
            f"{2 * km_lon:.0f} km. Pick a province-sized region, or widen the "
            f"coordinates.")


def coverage_gap(source_key, date_start, date_end):
    """Where the requested window sits against what the product covers;
    None when fully covered, else a dict naming the overlap."""
    low, high = SOURCES[source_key]["coverage"]
    overlap_start = max(date_start, low)
    overlap_end = min(date_end, high)
    if overlap_start > overlap_end:
        return {"covered": False, "overlap": None, "source_range": (low, high),
                "requested": (date_start, date_end)}
    partial = date_start < low or date_end > high
    return None if not partial else {
        "covered": True, "overlap": (overlap_start, overlap_end),
        "source_range": (low, high), "requested": (date_start, date_end),
    }


def clamp_to_coverage(source_key, date_start, date_end):
    """The requested window trimmed to what the product has, or None."""
    low, high = SOURCES[source_key]["coverage"]
    start = max(date_start, low)
    end = min(date_end, high)
    return (start, end) if start <= end else None


# ---------------------------------------------------------------------------
# Trend, season, remainder
# ---------------------------------------------------------------------------

def decompose(rows):
    """Split an XCO2 series into trend + seasonal + remainder (None if too
    short). Seasonal is each month's offset from its own year's mean, averaged
    across years — keeps the long-term rise out of the seasonal term."""
    if len(rows) < 8:
        return None

    days = np.array([_day_number(row["date"]) for row in rows], dtype=float)
    values = np.array([row["mean"] for row in rows], dtype=float)
    years_span = (days.max() - days.min()) / 365.25

    slope, intercept = np.polyfit(days, values, 1)
    trend = slope * days + intercept
    detrended = values - trend

    months = np.array([int(row["date"][5:7]) for row in rows])
    years = np.array([int(row["date"][:4]) for row in rows])

    seasonal_profile = None
    seasonal = np.zeros_like(values)
    if years_span >= MIN_YEARS_FOR_SEASONAL:
        per_year = []
        for year in sorted(set(years)):
            monthly = np.array([
                values[(years == year) & (months == month)].mean()
                if ((years == year) & (months == month)).any() else np.nan
                for month in range(1, 13)])
            if np.isnan(monthly).sum() > 2:      # skip a partial year
                continue
            per_year.append(monthly - np.nanmean(monthly))
        if per_year:
            seasonal_profile = np.nanmean(np.array(per_year), axis=0)
            seasonal_profile -= np.nanmean(seasonal_profile)
            seasonal = seasonal_profile[months - 1]

    remainder = detrended - seasonal

    return {
        "dates": [row["date"] for row in rows],
        "values": values.tolist(),
        "trend": trend.tolist(),
        "seasonal": seasonal.tolist(),
        "remainder": remainder.tolist(),
        "deseasonalised": (values - seasonal).tolist(),
        "slope_ppm_per_year": float(slope * 365.25),
        "years_span": float(years_span),
        # bool() needed: numpy.bool_ from the `>=` isn't JSON-serialisable.
        "has_trend": bool(years_span >= MIN_YEARS_FOR_TREND),
        "has_seasonal": bool(seasonal_profile is not None),
        "seasonal_profile": (None if seasonal_profile is None
                             else seasonal_profile.tolist()),
        "seasonal_amplitude": (None if seasonal_profile is None else
                               float(np.nanmax(seasonal_profile)
                                     - np.nanmin(seasonal_profile))),
        "seasonal_max_month": (None if seasonal_profile is None
                               else int(np.nanargmax(seasonal_profile)) + 1),
        "seasonal_min_month": (None if seasonal_profile is None
                               else int(np.nanargmin(seasonal_profile)) + 1),
        "remainder_std": float(np.std(remainder)),
        "first": rows[0]["date"], "last": rows[-1]["date"],
        "n": len(rows),
    }


def _day_number(day):
    return (date.fromisoformat(day) - date(2000, 1, 1)).days


def anomaly_between(aoi_rows, background_rows):
    """AOI minus background, after each has its own trend/season removed
    (raw difference isn't usable for CO2 — see WHY_LAND_COVER)."""
    aoi = decompose(aoi_rows)
    background = decompose(background_rows)
    if not aoi or not background:
        return None

    by_date = {day: value for day, value
               in zip(background["dates"], background["remainder"])}
    pairs = [(day, value - by_date[day])
             for day, value in zip(aoi["dates"], aoi["remainder"])
             if day in by_date]
    if len(pairs) < 8:
        return None

    differences = np.array([value for _, value in pairs])
    mean = float(differences.mean())
    noise = float(differences.std())
    return {
        "dates": [day for day, _ in pairs],
        "anomaly": differences.tolist(),
        "mean_anomaly": mean,
        "anomaly_noise": noise,
        "signal_to_noise": (mean / noise) if noise else None,
        "n": len(pairs),
        "aoi": aoi, "background": background,
    }


def classify_anomaly(value):
    """Map a deseasonalised anomaly in ppm to a level and a colour."""
    if value is None:
        return None, None
    for upper, label, colour in ANOMALY_LEVELS:
        if value < upper:
            return label, colour
    return ANOMALY_LEVELS[-1][1], ANOMALY_LEVELS[-1][2]


# ---------------------------------------------------------------------------
# NO2 -> combustion CO2
# ---------------------------------------------------------------------------

def infer_from_no2(delta_no2_umol_m2):
    """CO2 column an NO2 enhancement implies: the ratio converts NO2 to CO2,
    then dividing by the dry-air column converts that to ppm. None when
    there's no positive enhancement to infer from."""
    if delta_no2_umol_m2 is None or delta_no2_umol_m2 <= 0:
        return None
    air_umol_m2 = DRY_AIR_COLUMN_MOL_M2 * 1e6
    out = {}
    for name, ratio in EMISSION_RATIOS.items():
        out[name] = float(delta_no2_umol_m2 * ratio / air_umol_m2 * 1e6)
    out["ratios"] = dict(EMISSION_RATIOS)
    out["delta_no2"] = float(delta_no2_umol_m2)
    return out


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def inventory_totals(stats, bbox):
    """ODIAC stats -> readable figures: carbon is scaled to CO2 (44/12), cell
    area isn't square off the equator, and `count` is cells with data (not
    cells in the box), so totals are mean x count, not mean x area."""
    if not stats or stats.get("mean") is None:
        return None

    mid_lat = (bbox["N"] + bbox["S"]) / 2.0
    cell_lat, cell_lon = SOURCES["odiac"]["cell_deg"]
    cell_km2 = (cell_lat * 111.0) * (cell_lon * 111.0
                                     * max(np.cos(np.radians(mid_lat)), 0.01))

    km_lat = abs(bbox["N"] - bbox["S"]) * 111.0
    km_lon = (abs(bbox["E"] - bbox["W"]) * 111.0
              * max(np.cos(np.radians(mid_lat)), 0.01))
    area_km2 = km_lat * km_lon

    mean_c = max(stats["mean"], 0.0)
    emitting_cells = stats.get("count") or 0.0
    emitting_km2 = emitting_cells * cell_km2

    return {
        # Raw values from NASA's server; everything below is arithmetic on these.
        "raw_mean_tc_per_cell": stats["mean"],
        "raw_max_tc_per_cell": stats.get("max"),
        "raw_cell_count": emitting_cells,
        "raw_valid_percent": stats.get("valid_percent"),
        "area_km2": area_km2,
        "emitting_km2": emitting_km2,
        # Capped at 1: the service snaps its read window to whole cells, so
        # a small box can report slightly more emitting area than it has.
        "emitting_share": (min(emitting_km2 / area_km2, 1.0)
                           if area_km2 else None),
        "cell_km2": cell_km2,
        # Per km2 of emitting land, not of the whole area.
        "mean_tco2_per_km2_month": mean_c * CARBON_TO_CO2 / cell_km2,
        "peak_tco2_per_km2_month": (max(stats.get("max") or 0.0, 0.0)
                                    * CARBON_TO_CO2 / cell_km2),
        # Single most intense cell, annualised to Mt/yr.
        "peak_mtco2_per_year_cell": (max(stats.get("max") or 0.0, 0.0)
                                     * CARBON_TO_CO2 * 12.0 / 1e6),
        "p98_tco2_per_km2_month": (max(stats.get("percentile_98") or 0.0, 0.0)
                                   * CARBON_TO_CO2 / cell_km2),
        "total_mtco2_per_year": (mean_c * emitting_cells * CARBON_TO_CO2
                                 * 12.0 / 1e6),
    }
