"""Provide descriptive intervals and fixed-bin EDA summaries."""

from typing import Any

import numpy as np
import pandas as pd


def wilson_interval(success: Any, total: Any) -> tuple[Any, Any]:
    """Calculate descriptive Wilson intervals for a single cohort or entity.

    Args:
        success: Observed binary successes.
        total: Observed binary trials.

    Returns:
        Lower and upper 95 percent Wilson bounds. Zero support yields NaN.

    Notes:
        These intervals do not correct for item selection or repeated users.
    """
    count = np.asarray(total, dtype=float)
    hits = np.asarray(success, dtype=float)
    safe = np.where(count > 0, count, np.nan)
    rate = hits / safe
    correction = 1 + 1.96**2 / safe
    center = (rate + 1.96**2 / (2 * safe)) / correction
    half = (
        1.96 * np.sqrt(rate * (1 - rate) / safe + 1.96**2 / (4 * safe**2)) / correction
    )
    return center - half, center + half


def summarize_bins(
    frame: pd.DataFrame, feature: str, target: str, edges: list[float]
) -> pd.DataFrame:
    """Summarize observed binary outcomes within declared left-closed bins.

    Args:
        frame: Single-cohort observations.
        feature: Numeric feature to bin.
        target: Binary outcome column.
        edges: Increasing bin boundaries.

    Returns:
        Nonempty bins with support, outcomes, rates and descriptive intervals.
    """
    labels = [
        (
            str(int(low))
            if high == low + 1
            else (f"{int(low)}+" if np.isinf(high) else f"{int(low)}–{int(high) - 1}")
        )
        for low, high in zip(edges[:-1], edges[1:])
    ]
    groups = pd.cut(frame[feature], edges, right=False, labels=labels)
    result = (
        frame.assign(bin=groups)
        .groupby("bin", observed=True)[target]
        .agg(users="size", positives="sum")
        .reset_index()
    )
    result["bin"] = result["bin"].astype(str)
    result["purchase_rate"] = result["positives"] / result["users"]
    result["lower"], result["upper"] = wilson_interval(
        result["positives"], result["users"]
    )
    result["feature"] = feature
    return result
