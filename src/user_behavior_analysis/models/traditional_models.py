"""Represent chronological inputs and version paths for model comparison."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from user_behavior_analysis.models.sampling_models import PartitionEvidence

MODEL_FAMILIES = ("logistic_regression", "xgboost", "lightgbm")


@dataclass(frozen=True)
class TraditionalSettings:
    """Hold versioned destinations and the predeclared computational budget.

    Attributes:
        sampling_catalog: Approved 3.1 sample catalog.
        data_root: New local trained models and prediction directory.
        report_dir: New aggregate report directory.
        catalog: New catalog created only after scoring and audit pass.
        seed: Fixed TPE and training seed.
        threads: Maximum native threads per model.
        trials_per_model: Total Optuna trials per model, including the baseline.
    """

    sampling_catalog: Path
    data_root: Path
    report_dir: Path
    catalog: Path
    seed: int
    threads: int
    trials_per_model: int


@dataclass(frozen=True)
class TemporalPlan:
    """Hold metadata for the primary time backtest and its audited inputs.

    Attributes:
        source: File fingerprint of the stage 3.1 sampling catalog.
        features: The approved history-only model input columns, in order.
        anchors: Exclusive feature cutoff for every split.
        partitions: File record and class counts of each chronological split.
    """

    source: dict[str, Any]
    features: tuple[str, ...]
    anchors: dict[str, str]
    partitions: dict[str, PartitionEvidence]


@dataclass(frozen=True)
class LabeledMatrix:
    """A numerical feature matrix and its separate binary target.

    Attributes:
        values: Aligned numerical feature rows.
        target: Binary outcomes in the same row order.
    """

    values: np.ndarray
    target: np.ndarray
