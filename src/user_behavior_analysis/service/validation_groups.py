"""Assign every scalar to one experiment family and define history-only cohorts."""

from typing import Any

import numpy as np
import pandas as pd

RF_FIELDS = {
    "user_rf_recency_score",
    "user_rf_frequency_score",
    "user_purchase_count_proxy_score",
    "user_rf_segment",
    "user_lifecycle_state",
}
COHORT_COLUMNS = [
    "user_id",
    "item_id",
    "target",
    "user_activity_level_7d",
    "user_observed_age_days",
    "pair_svd_available",
    "pair_cooc_graph_known",
]


def feature_group(definition: dict[str, Any]) -> str:
    """Assign one existing scalar without changing its persisted definition.

    Args:
        definition: Original field name and family metadata.

    Returns:
        One exhaustive experiment group.
    """
    family = definition["family"]
    advanced = {
        "SVD隐式特征": "svd",
        "共现与关联规则": "cooccurrence",
        "小时序列": "sequence",
        "日历": "calendar",
    }
    if family in advanced:
        return advanced[family]
    if family in {"基础统计", "生命周期"} or (
        family == "生命周期与RF代理" and definition["name"] not in RF_FIELDS
    ):
        return "basic"
    return "business"


def business_protected(definition: dict[str, Any]) -> bool:
    """Protect explicit RF and historical funnel semantics from weak-score deletion.

    Args:
        definition: Existing feature metadata.

    Returns:
        Whether the field requires an explicit business retention decision.
    """
    return definition["family"] == "严格小时漏斗" or definition["name"] in RF_FIELDS


def cohort_masks(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Apply fixed, label-independent activity, observation and coverage rules.

    Args:
        frame: Features with the required cohort columns.

    Returns:
        Overlapping Boolean masks; new-observed does not mean newly registered.
    """
    return {
        "all": np.ones(len(frame), dtype=bool),
        "low_activity": frame["user_activity_level_7d"].to_numpy() == 0,
        "high_activity": frame["user_activity_level_7d"].to_numpy() >= 2,
        "new_observed": frame["user_observed_age_days"].to_numpy() <= 3,
        "svd_available": frame["pair_svd_available"].to_numpy() == 1,
        "svd_unavailable": frame["pair_svd_available"].to_numpy() == 0,
        "cooccurrence_available": frame["pair_cooc_graph_known"].to_numpy() == 1,
        "cooccurrence_unavailable": frame["pair_cooc_graph_known"].to_numpy() == 0,
    }
