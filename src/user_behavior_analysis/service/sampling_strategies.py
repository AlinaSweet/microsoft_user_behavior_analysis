"""Apply deterministic class-imbalance treatments to training rows only."""

from dataclasses import dataclass

import numpy as np
from sklearn.neighbors import NearestNeighbors  # type: ignore[import-untyped]

from user_behavior_analysis.models.sampling_models import SamplingSettings
from user_behavior_analysis.service.wide_contracts import require_contract

STRATEGIES = ("natural", "smote", "undersample", "class_weight")


@dataclass(frozen=True)
class TrainingVariant:
    """Prepared training rows, fit weights and synthetic-row counts.

    Attributes:
        values: Constant-schema numerical training features.
        target: Binary training outcomes.
        weights: Per-class objective weights with mean weight one.
        synthetic_rows: Additional positive vectors generated in feature space.
    """

    values: np.ndarray
    target: np.ndarray
    weights: dict[int, float]
    synthetic_rows: int = 0


def _interpolate_positive(
    positives: np.ndarray, count: int, neighbors: int, generator: np.random.Generator
) -> np.ndarray:
    """Generate vectors on line segments between distinct minority training rows.

    Args:
        positives: Imputed and scaled minority-only training matrix.
        count: Required number of synthetic positives.
        neighbors: Configured maximum number of neighbors.
        generator: Seeded training-only random generator.

    Returns:
        Synthetic training vectors in the same continuous feature space.
    """
    require_contract(len(positives) > 1, "SMOTE requires at least two positives")
    bound = min(neighbors, len(positives) - 1)
    search = NearestNeighbors(n_neighbors=bound, algorithm="brute").fit(positives)
    nearest = search.kneighbors(return_distance=False)
    base = generator.integers(len(positives), size=count)
    neighbor = nearest[base, generator.integers(bound, size=count)]
    start = positives[base]
    mix = generator.random((count, 1), dtype=np.float32)
    return np.asarray(start + mix * (positives[neighbor] - start))


def prepare_training(
    strategy: str, values: np.ndarray, target: np.ndarray, settings: SamplingSettings
) -> TrainingVariant:
    """Prepare one natural, SMOTE, undersampled or weighted training input.

    Args:
        strategy: One of the four predeclared treatments.
        values: The transformed training matrix only.
        target: Original binary training outcomes only.
        settings: Fixed seed, neighbor count and class-ratio policy.

    Returns:
        Data and weights used in the fixed logistic control.
    """
    positive = np.flatnonzero(target == 1)
    negative = np.flatnonzero(target == 0)
    require_contract(
        min(len(positive), len(negative)) > 0
        and len(positive) + len(negative) == len(values) == len(target),
        "Treatment requires aligned training rows from both binary classes",
    )
    ratio = settings.negative_per_positive
    generator = np.random.default_rng(settings.seed)
    uniform = {0: 1.0, 1: 1.0}
    if strategy == "natural":
        return TrainingVariant(values, target, uniform)
    if strategy == "class_weight":
        multiplier = max(1.0, len(negative) / (ratio * len(positive)))
        normalized = len(target) / (len(negative) + multiplier * len(positive))
        return TrainingVariant(
            values, target, {0: normalized, 1: multiplier * normalized}
        )
    if strategy == "undersample":
        kept = min(len(negative), ratio * len(positive))
        sampled = generator.choice(negative, size=kept, replace=False)
        indices = np.sort(np.concatenate((positive, sampled)))
        return TrainingVariant(values[indices], target[indices], uniform)
    if strategy == "smote":
        desired = (len(negative) + ratio - 1) // ratio
        count = max(0, desired - len(positive))
        if count == 0:
            return TrainingVariant(values, target, uniform)
        extra = _interpolate_positive(
            values[positive], count, settings.smote_neighbors, generator
        )
        return TrainingVariant(
            np.concatenate((values, extra)),
            np.concatenate((target, np.ones(count, dtype=target.dtype))),
            uniform,
            count,
        )
    raise ValueError("Unknown training strategy: " + strategy)
