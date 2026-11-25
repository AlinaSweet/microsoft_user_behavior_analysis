"""Assess cold-start support, popularity slices and full-test error profiles."""

from typing import Any

import numpy as np
import pandas as pd

from user_behavior_analysis.models.sequence_models import SequenceSplit
from user_behavior_analysis.service.validation_metrics import prediction_metrics
from user_behavior_analysis.service.wide_contracts import require_contract


def split_meta_validation(keys: pd.DataFrame, seed: int) -> np.ndarray:
    """Split the intermediate cutoff into user-disjoint fitting and decision groups.

    Args:
        keys: Candidate keys at the intermediate validation cutoff.
        seed: Fixed group-assignment seed.

    Returns:
        Boolean membership of the approximately 65 percent meta-fitting user group.
    """
    users = np.unique(keys["user_id"].to_numpy())
    require_contract(len(users) >= 2, "Need two or more validation users")
    selected = np.random.default_rng(seed).permutation(users)[
        : max(1, 65 * len(users) // 100)
    ]
    return keys["user_id"].isin(selected).to_numpy(dtype=np.bool_)


def test_context(train: SequenceSplit, test: SequenceSplit) -> pd.DataFrame:
    """Assign cold-start definitions and item support from training history only.

    Args:
        train: Complete approved training candidates, before negative sampling.
        test: Complete labeled test candidates.

    Returns:
        One row per test candidate with prior support and available history length.
    """
    training_item_support = train.keys["item_id"].value_counts()
    support = test.keys["item_id"].map(training_item_support).fillna(0).astype("int64")
    recent = test.history.hour.amax(dim=1)[test.history_rows].numpy()
    return pd.DataFrame(
        {
            "user_seen_in_training": test.keys["user_id"].isin(train.keys["user_id"]),
            "training_users_for_item": support,
            "retained_history_hours": recent,
            "item_in_embedding_vocabulary": (test.candidate[:, 0] > 1).numpy(),
        }
    )


def slice_metrics(
    target: np.ndarray,
    scores: dict[str, np.ndarray],
    thresholds: dict[str, float],
    context: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Measure fixed thresholds on data-supported cold-start and long-tail slices.

    Args:
        target: Natural chronological test outcomes.
        scores: Evaluated individuals and meta classifier, with matching row order.
        thresholds: Frozen validation thresholds.
        context: Training-defined support and observed histories.

    Returns:
        Per-slice row counts, ranking and confusion metrics with support labels.
    """
    seen = context["user_seen_in_training"]
    items = context["training_users_for_item"]
    masks = {
        "user_seen_in_training": seen,
        "user_unseen_in_training": ~seen,
        "user_at_most_3_retained_hours": context["retained_history_hours"].le(3),
        "item_unseen_in_training": items.eq(0),
        "item_long_tail_1_to_2_training_users": items.between(1, 2),
        "item_more_than_2_training_users": items.gt(2),
    }
    rows = []
    for name, mask in masks.items():
        indexes = mask.to_numpy(dtype=np.bool_)
        outcomes = target[indexes]
        for model, score in scores.items():
            summary = prediction_metrics(outcomes, score[indexes], thresholds[model])
            rows.append(
                dict(
                    summary,
                    slice=name,
                    model=model,
                    support=(
                        "low_positive_support"
                        if summary["positives"] < 20
                        else "adequate"
                    ),
                )
            )
    return rows


def error_profiles(
    test: SequenceSplit,
    scores: dict[str, np.ndarray],
    thresholds: dict[str, float],
    features: tuple[str, ...],
    context: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Summarize standardized feature values and support for all confusion groups.

    Args:
        test: Natural labels and train-standardized historical dense features.
        scores: Models to diagnose without threshold refitting.
        thresholds: Frozen thresholds.
        features: Ordered model feature names.
        context: Training-derived item support and available histories.

    Returns:
        Full test group counts and aggregate means, without individual IDs.
    """
    rows = []
    numeric = pd.DataFrame(test.dense.numpy(), columns=list(features))
    numeric = pd.concat((numeric, context), axis=1)
    positive = test.target == 1
    for model, score in scores.items():
        predicted = score >= thresholds[model]
        groups = {
            "true_positive": positive & predicted,
            "false_positive": ~positive & predicted,
            "false_negative": positive & ~predicted,
            "true_negative": ~positive & ~predicted,
        }
        for label, mask in groups.items():
            summary = numeric.loc[mask].mean().to_dict()
            rows.append(dict(summary, model=model, case=label, rows=int(mask.sum())))
    return rows
