"""Define the stage-three sample protocols and registered partition evidence."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import TypedDict

from user_behavior_analysis.models.validation_models import ValidationSettings

SPLITS = ("train", "validation", "test")
PROTOCOLS = ("time_backtest", "grouped_721")


@dataclass(frozen=True)
class SamplingSettings:
    """Hold immutable inputs, new version paths, and fixed sampling parameters.

    Attributes:
        validation: Approved stage-two label and sample configuration.
        data_root: New local Parquet partitions and trained baselines.
        report_dir: New directory for aggregate evidence and model selection.
        catalog: New catalog published only after a successful run.
        features: Ordered history-only continuous feature names.
        seed: Fixed pair ordering and sampling seed.
        negative_per_positive: Target training ratio for all imbalance strategies.
        smote_neighbors: Maximum minority neighbors used for interpolation.
    """

    validation: ValidationSettings
    data_root: Path
    report_dir: Path
    catalog: Path
    features: tuple[str, ...]
    seed: int
    negative_per_positive: int
    smote_neighbors: int


class PartitionEvidence(TypedDict):
    """An exact split size, class distribution, pair count and file fingerprint."""

    file: dict[str, Any]
    rows: int
    positives: int
    negatives: int
    positive_rate: float
    row_share: float
    pair_groups: int
    positive_pair_groups: int
    first_anchor: str
    last_anchor: str
