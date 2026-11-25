"""Measure fixed predictions with class support and user-cluster uncertainty."""

from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score  # type: ignore[import-untyped]
from sklearn.metrics import brier_score_loss
from sklearn.metrics import confusion_matrix  # type: ignore[import-untyped]
from sklearn.metrics import log_loss
from sklearn.metrics import precision_recall_curve
from sklearn.metrics import roc_auc_score  # type: ignore[import-untyped]


def explanation_rows(target: np.ndarray, size: int, seed: int) -> np.ndarray:
    """Select a fixed class-balanced explanation sample after model evaluation.

    Args:
        target: Complete untouched test labels.
        size: Maximum number of chosen cases.
        seed: Independent analysis sampling seed.

    Returns:
        Stable sorted test positions, with both labels where supported.
    """
    random = np.random.default_rng(seed)
    positions = [np.flatnonzero(target == label) for label in (0, 1)]
    return np.sort(
        np.concatenate(
            [
                random.choice(rows, min(size // 2, len(rows)), replace=False)
                for rows in positions
            ]
        )
    )


def prediction_metrics(
    target: np.ndarray, scores: np.ndarray, threshold: float = 0.5
) -> dict[str, Any]:
    """Evaluate complete predictions without tuning a threshold on their labels.

    Args:
        target: Observed pair-level binary outcomes.
        scores: Predicted purchase probabilities.
        threshold: Predeclared classification threshold.

    Returns:
        Exact AUC/AP, confusion counts and explicit single-class limitations.
    """
    positive = int(target.sum())
    negative = len(target) - positive
    supported = min(positive, negative) > 0
    matrix = confusion_matrix(target, scores >= threshold, labels=[0, 1])
    true_negative, false_positive, false_negative, true_positive = map(
        int, matrix.ravel()
    )
    return {
        "rows": len(target),
        "positives": positive,
        "negatives": negative,
        "positive_rate": positive / len(target) if len(target) else None,
        "roc_auc": float(roc_auc_score(target, scores)) if supported else None,
        "average_precision": (
            float(average_precision_score(target, scores)) if supported else None
        ),
        "metric_status": "available" if supported else "single_or_empty_class",
        "accuracy": (
            (true_positive + true_negative) / len(target) if len(target) else None
        ),
        "precision": (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0
        ),
        "recall": true_positive / positive if positive else None,
        "f1": (
            2 * true_positive / (2 * true_positive + false_positive + false_negative)
            if positive + false_positive
            else 0
        ),
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_positive": true_positive,
        "threshold": threshold,
    }


def validation_f1_threshold(target: np.ndarray, scores: np.ndarray) -> float:
    """Choose the highest validation threshold achieving maximum F1.

    Args:
        target: Natural validation labels.
        scores: Fixed model probabilities in the same row order.

    Returns:
        Threshold to freeze before test scoring.
    """
    precision, recall, thresholds = precision_recall_curve(target, scores)
    numerator = 2 * precision[:-1] * recall[:-1]
    denominator = precision[:-1] + recall[:-1]
    f1 = np.divide(
        numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0
    )
    return float(thresholds[np.flatnonzero(f1 == f1.max())[-1]])


def probability_metrics(
    target: np.ndarray, scores: np.ndarray, threshold: float
) -> dict[str, Any]:
    """Add probability error scores to the common binary evaluation metrics.

    Args:
        target: Natural held-out labels.
        scores: Probabilities from a train-fitted model.
        threshold: Fixed threshold selected on validation.

    Returns:
        Ranking, threshold, log-loss and Brier results.
    """
    result = prediction_metrics(target, scores, threshold)
    result.update(
        log_loss=float(log_loss(target, scores, labels=[0, 1])),
        brier_score=float(brier_score_loss(target, scores)),
    )
    return result


def _weighted_rank_auc(
    target: np.ndarray, weights: np.ndarray, starts: np.ndarray
) -> float:
    """Compute exact tie-aware AUC in a fixed ascending score order.

    Args:
        target: Labels sorted by an unchanged model score.
        weights: User-cluster multiplicities in the same order.
        starts: Start indices of tied-score groups.

    Returns:
        Weighted AUC, or NaN when a bootstrap has only one class.
    """
    positive = np.add.reduceat(weights * target, starts)
    negative = np.add.reduceat(weights * (1 - target), starts)
    denominator = positive.sum() * negative.sum()
    if denominator == 0:
        return float("nan")
    return float(
        np.sum(positive * (np.cumsum(negative) - 0.5 * negative)) / denominator
    )


def clustered_auc_deltas(
    target: np.ndarray,
    predictions: dict[str, np.ndarray],
    users: np.ndarray,
    repeats: int,
    seed: int,
) -> dict[str, Any]:
    """Estimate paired AUC differences without treating one user's rows as independent.

    Args:
        target: Complete binary outcomes of one evaluation cutoff.
        predictions: Same-row model probabilities, including business baseline.
        users: Integer cluster codes aligned with the outcomes.
        repeats: Number of user-cluster bootstrap replicates.
        seed: Fixed resampling seed shared across all models.

    Returns:
        Percentile intervals for each model's AUC difference versus business.
    """
    total_users = int(users.max()) + 1
    generator = np.random.default_rng(seed)
    multiplicities = [
        np.bincount(
            generator.integers(0, total_users, total_users), minlength=total_users
        )
        for _ in range(repeats)
    ]
    estimates = {}
    for name, scores in predictions.items():
        order = np.argsort(scores, kind="stable")
        ordered_scores = scores[order]
        starts = np.r_[0, np.flatnonzero(np.diff(ordered_scores)) + 1]
        ordered_target, ordered_users = target[order], users[order]
        estimates[name] = np.array(
            [
                _weighted_rank_auc(ordered_target, weights[ordered_users], starts)
                for weights in multiplicities
            ]
        )
    return {
        name: {
            "reference": "business",
            "method": "paired user-cluster percentile bootstrap",
            "replicates": repeats,
            "confidence": 0.95,
            "lower": float(np.nanquantile(values - estimates["business"], 0.025)),
            "upper": float(np.nanquantile(values - estimates["business"], 0.975)),
        }
        for name, values in estimates.items()
    }
