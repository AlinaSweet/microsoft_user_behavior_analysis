"""Cross-fit purchase-rate encodings by training user and freeze inference maps."""

import hashlib

import numpy as np
import pandas as pd

from user_behavior_analysis.models.encoding_models import TargetEncodingState
from user_behavior_analysis.service.wide_contracts import require_contract


def user_fold(user_id: str, folds: int) -> int:
    """Assign every row of one user to the same deterministic held-out fold.

    Args:
        user_id: Exact source user identifier.
        folds: Number of user folds.

    Returns:
        Stable fold index independent of labels or source row order.
    """
    return int.from_bytes(hashlib.sha256(user_id.encode()).digest()[:8], "big") % folds


def fit_target_encoding(
    frame: pd.DataFrame,
    column: str,
    folds: int,
    smoothing: float,
    available_at: str,
) -> TargetEncodingState:
    """Fit training and fold-excluded maps with fold-excluded global priors.

    Args:
        frame: Only the declared training cutoff, with user_id and target.
        column: Existing categorical feature, never a future fact.
        folds: User-group fold count.
        smoothing: Fixed nonnegative prior strength.
        available_at: Latest exclusive end of the training label windows.

    Returns:
        Frozen full-training and out-of-user-fold mappings.

    Raises:
        ValueError: Targets, groups or fixed parameters are invalid.
    """
    require_contract(folds >= 2 and smoothing > 0, "Encoding parameter bounds")
    require_contract(
        bool(frame.target.isin([0, 1]).all()), "Mature binary labels required"
    )
    users = {
        str(value): user_fold(str(value), folds) for value in frame.user_id.unique()
    }
    assignments = frame.user_id.map(users)
    require_contract(
        assignments.nunique() == folds, "Insufficient training user groups"
    )
    model = TargetEncodingState(column, users, {}, {}, smoothing, available_at)
    for fold in [-1] + list(range(folds)):
        subset = frame if fold == -1 else frame.loc[assignments != fold]
        key = "full" if fold == -1 else str(fold)
        prior = float(subset.target.mean())
        grouped = subset.groupby(column, observed=True).target.agg(["sum", "count"])
        model.priors[key] = prior
        model.maps[key] = {
            str(category): float(
                (row["sum"] + smoothing * prior) / (row["count"] + smoothing)
            )
            for category, row in grouped.iterrows()
        }
    return model


def encode_target(
    frame: pd.DataFrame, state: TargetEncodingState, training: bool
) -> np.ndarray:
    """Encode held-out training users or later inference rows without refitting.

    Args:
        frame: Bounded feature rows; inference target values are ignored.
        state: Training-only category and group maps.
        training: True exclusively for cross-fitted training observations.

    Returns:
        One float32 probability-like predictor per candidate row.

    Raises:
        ValueError: A training user is unknown or inference predates label maturity.
    """
    if not training:
        if "as_of_time" in frame:
            require_contract(
                bool(
                    (
                        pd.to_datetime(frame.as_of_time)
                        >= pd.Timestamp(state.available_at)
                    ).all()
                ),
                "Encoder labels not yet mature",
            )
        return (
            frame[state.column]
            .map(state.maps["full"])
            .fillna(state.priors["full"])
            .to_numpy(dtype=np.float32)
        )
    assignments = frame.user_id.map(state.user_folds)
    require_contract(bool(assignments.notna().all()), "Unknown cross-fitting user")
    result = np.empty(len(frame), dtype=np.float32)
    for fold in assignments.unique():
        mask = assignments.to_numpy() == fold
        key = str(int(fold))
        result[mask] = (
            frame.loc[mask, state.column]
            .map(state.maps[key])
            .fillna(state.priors[key])
            .to_numpy(dtype=np.float32)
        )
    return result
