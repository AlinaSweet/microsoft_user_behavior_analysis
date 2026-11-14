"""Describe user-group cross-fitted target encoding and frozen sparse projections."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from user_behavior_analysis.models.validation_models import FeatureTransform
from user_behavior_analysis.models.validation_models import ValidationSettings


@dataclass(frozen=True)
class CompletionSettings:
    """Keep new completion artifacts separate from accepted historical inputs.

    Attributes:
        validation: Existing immutable pair-label and sample configuration.
        data_root: New transformed matrices, sidecars and models.
        report_dir: Current stage-two delivery documents and numerical evidence.
        catalog: New completion manifest.
        options: Declared encoding, projection and comparison parameters.
    """

    validation: ValidationSettings
    data_root: Path
    report_dir: Path
    catalog: Path
    options: dict[str, Any]


@dataclass
class TargetEncodingState:
    """Freeze target maps without any held-out user's labels in its training map.

    Attributes:
        column: High-dimensional categorical input.
        user_folds: Stable training-user fold assignments.
        maps: Full-training and fold-excluded smoothed category maps.
        priors: Matching full-training or fold-excluded purchase priors.
        smoothing: Fixed prior pseudo-observation count.
        available_at: Time all fitting labels become observable.
    """

    column: str
    user_folds: dict[str, int]
    maps: dict[str, dict[str, float]]
    priors: dict[str, float]
    smoothing: float
    available_at: str


@dataclass
class CompletionTransform:
    """Combine frozen numeric preparation, target encoding and sparse embedding.

    Attributes:
        numeric: Prepared numeric and remaining small categorical fields.
        target: User-group cross-fitted encoding model.
        vocabularies: Training-only vocabularies for three sparse categorical fields.
        components: Frozen sparse SVD projection.
        embedding_mean: Training projection means.
        embedding_scale: Training projection standard deviations.
    """

    numeric: FeatureTransform
    target: TargetEncodingState
    vocabularies: dict[str, list[str]]
    components: np.ndarray
    embedding_mean: np.ndarray
    embedding_scale: np.ndarray
