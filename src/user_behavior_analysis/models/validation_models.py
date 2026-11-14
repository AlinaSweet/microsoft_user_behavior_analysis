"""Hold confined validation paths and train-fitted preprocessing state."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationSettings:
    """Describe immutable inputs, new output versions and experiment options.

    Attributes:
        wide_catalog: Previously approved feature-only input catalog.
        label_root: New dense pair-target files.
        sample_root: New joined sample and model files.
        report_dir: Small evidence and result files.
        catalog: Final successful delivery catalog.
        options: Explicit split, sampling, fitting and screening parameters.
    """

    wide_catalog: Path
    label_root: Path
    sample_root: Path
    report_dir: Path
    catalog: Path
    options: dict[str, Any]


@dataclass
class FeatureTransform:
    """Keep preprocessing learned exclusively from complete training rows.

    Attributes:
        columns: Scalar names, excluding keys and targets.
        medians: Training nonmissing median for numeric imputation.
        means: Training numeric mean after imputation.
        scales: Training numeric standard deviation after imputation.
        categories: Training-only ordered vocabularies for categorical fields.
        missing_indicators: Numeric fields having missing training observations.
    """

    columns: list[str]
    medians: dict[str, float]
    means: dict[str, float]
    scales: dict[str, float]
    categories: dict[str, list[str]]
    missing_indicators: list[str]
