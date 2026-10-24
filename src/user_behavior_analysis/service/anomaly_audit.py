"""Recompute exact activity thresholds from independently reduced histograms."""

import math
from pathlib import Path
from typing import TypedDict
from typing import cast

import dask.dataframe as dd

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.cleaning_models import AnomalyMetric
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.service.runtime import resource_plan
from user_behavior_analysis.service.runtime import start_client


class ActivitySummary(TypedDict):
    """Describe exact population statistics for an integer-count distribution."""

    entities: int
    q1: float
    q3: float
    iqr_lower: float
    iqr_upper: float
    mean: float
    population_std: float
    sigma_lower: float
    sigma_upper: float
    iqr_flagged_entities: int
    sigma_flagged_entities: int


class AnomalyAudit(TypedDict):
    """Record an independent threshold reconstruction and comparison results."""

    entity: str
    status: str
    actual: ActivitySummary
    checks: dict[str, bool]


def _order_statistic(histogram: dict[int, int], rank: int) -> int:
    """Find a zero-based ordered value without expanding a count histogram.

    Args:
        histogram: Activity counts mapped to positive entity frequencies.
        rank: Nonnegative position in the sorted, conceptually expanded population.

    Returns:
        The event-count value occupying that position.

    Raises:
        ValueError: The histogram does not contain enough observations for the rank.
    """
    accumulated = 0
    for value, frequency in sorted(histogram.items()):
        accumulated += frequency
        if accumulated > rank:
            return value
    raise ValueError("Activity rank exceeds the histogram population")


def _quantile(histogram: dict[int, int], population: int, probability: float) -> float:
    """Interpolate an exact quantile from an activity-count histogram.

    Args:
        histogram: Positive event counts mapped to positive entity frequencies.
        population: Positive total frequency matching the histogram.
        probability: Requested quantile in the inclusive range [0, 1].

    Returns:
        The linearly interpolated value at (population - 1) * probability.

    Raises:
        ValueError: A required ordered position is absent from the histogram.

    Notes:
        The caller is responsible for validating population and probability.
    """
    position = (population - 1) * probability
    lower = math.floor(position)
    fraction = position - lower
    return (
        _order_statistic(histogram, lower) * (1 - fraction)
        + _order_statistic(histogram, math.ceil(position)) * fraction
    )


def summarize_activity_histogram(histogram: dict[int, int]) -> ActivitySummary:
    """Compute exact thresholds from a small count-frequency histogram.

    Args:
        histogram: Positive event counts mapped to positive entity frequencies.

    Returns:
        Linearly interpolated quartiles, population moments, and flag counts.

    Raises:
        ValueError: The histogram is empty or contains nonpositive values.
    """
    if not histogram or any(
        value <= 0 or frequency <= 0 for value, frequency in histogram.items()
    ):
        raise ValueError("Activity histogram must have positive counts and frequencies")
    population = sum(histogram.values())
    q1 = _quantile(histogram, population, 0.25)
    q3 = _quantile(histogram, population, 0.75)
    mean = (
        math.fsum(value * frequency for value, frequency in histogram.items())
        / population
    )
    variance = (
        math.fsum(
            frequency * (value - mean) ** 2 for value, frequency in histogram.items()
        )
        / population
    )
    deviation = math.sqrt(variance)
    iqr_lower, iqr_upper = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    sigma_lower, sigma_upper = mean - 3 * deviation, mean + 3 * deviation
    return {
        "entities": population,
        "q1": q1,
        "q3": q3,
        "iqr_lower": iqr_lower,
        "iqr_upper": iqr_upper,
        "mean": mean,
        "population_std": deviation,
        "sigma_lower": sigma_lower,
        "sigma_upper": sigma_upper,
        "iqr_flagged_entities": sum(
            frequency
            for value, frequency in histogram.items()
            if value < iqr_lower or value > iqr_upper
        ),
        "sigma_flagged_entities": sum(
            frequency
            for value, frequency in histogram.items()
            if value < sigma_lower or value > sigma_upper
        ),
    }


def audit_activity_anomalies(
    config: ProjectConfig, directory: Path, expected: list[AnomalyMetric]
) -> list[AnomalyAudit]:
    """Rebuild all user/item counts using Dask and compare exact thresholds.

    Args:
        config: Bounded Dask worker settings.
        directory: Complete cleaned Parquet event relation.
        expected: Recorded entity-count thresholds from the SQLite pipeline.

    Returns:
        Separate comparisons for each entity distribution.

    Notes:
        Only small count-frequency histograms reach the driver. Complete user
        or item ID count tables are not collected into driver memory.
    """
    path = project_output_path(directory)
    frame = dd.read_parquet(str(path), columns=["user_id", "item_id"])
    results: list[AnomalyAudit] = []
    with start_client(config, resource_plan(config)) as client:
        for metric in expected:
            column = {"user": "user_id", "item": "item_id"}[metric["entity"]]
            counts = frame.groupby(column).size(split_out=16)
            frequencies = client.compute(counts.value_counts(split_out=1)).result()
            histogram = {int(value): int(count) for value, count in frequencies.items()}
            actual = summarize_activity_histogram(histogram)
            expected_numeric = {
                name: float(value)
                for name, value in metric.items()
                if isinstance(value, (int, float))
            }
            checks = {
                name: math.isclose(
                    float(cast(float | int, value)),
                    expected_numeric[name],
                    rel_tol=1e-10,
                    abs_tol=1e-8,
                )
                for name, value in actual.items()
            }
            results.append(
                {
                    "entity": metric["entity"],
                    "status": "passed" if all(checks.values()) else "failed",
                    "actual": actual,
                    "checks": checks,
                }
            )
    return results
