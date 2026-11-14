"""Screen feature groups using training rows only and audit cohort support."""

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif  # type: ignore

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.dao.validation_repository import verified_sample_manifest
from user_behavior_analysis.models.validation_models import ValidationSettings
from user_behavior_analysis.service.validation_groups import business_protected
from user_behavior_analysis.service.validation_groups import cohort_masks
from user_behavior_analysis.service.validation_groups import feature_group
from user_behavior_analysis.service.validation_preprocessing import (
    fit_transform_contract,
)
from user_behavior_analysis.service.validation_preprocessing import training_profiles
from user_behavior_analysis.service.validation_preprocessing import transform_record
from user_behavior_analysis.service.wide_contracts import require_contract


def _mi_values(
    frame: pd.DataFrame, definitions: list[dict[str, Any]], seed: int
) -> dict[str, float]:
    """Estimate dependence with explicit discrete/continuous field semantics.

    Args:
        frame: Deterministic training-only sample with a binary target.
        definitions: Eligible fields from one feature group.
        seed: Reproducible estimator random seed.

    Returns:
        Per-field mutual information in nats, without a causal interpretation.
    """
    if not definitions:
        return {}
    columns, discrete = [], []
    for definition in definitions:
        series = frame[definition["name"]]
        category = definition["dtype"] == "category"
        if category:
            values = pd.Categorical(series.fillna("__missing__")).codes
        else:
            median = series.median() if series.notna().any() else 0
            values = series.fillna(median).to_numpy(dtype=np.float64)
        columns.append(values)
        discrete.append(category or definition["dtype"].startswith("int"))
    values = mutual_info_classif(
        np.column_stack(columns),
        frame["target"].to_numpy(),
        discrete_features=np.array(discrete),
        random_state=seed,
        n_jobs=1,
    )
    return dict(zip([d["name"] for d in definitions], map(float, values)))


def _eligible_profile(row: dict[str, Any], options: dict[str, Any]) -> tuple[bool, str]:
    """Apply declared first-round rules without using later cutoffs.

    Args:
        row: Full training profile with group and protection metadata.
        options: Declared thresholds and group caps.

    Returns:
        Eligibility and explicit decision reason.
    """
    if row["nonnull"] == 0:
        return False, "all_missing_in_train"
    constant = (
        row["distinct"] <= 1 if row["dtype"] == "category" else row["variance"] == 0
    )
    if constant:
        return False, "constant_in_train; business meaning retained in dictionary"
    if row["window_days"] == 30:
        return False, "deferred_30d_incomplete_at_all_labeled_cutoffs"
    if row["group"] == "calendar":
        return False, "single_training_cutoff_calendar_not_learnable"
    if (
        row["missing_rate"] >= options["missing_limit"]
        and not row["protected"]
        and row["group"] not in {"svd", "cooccurrence"}
    ):
        return False, "training_missing_rate_limit"
    return True, "round_one_passed"


def _select_group(
    frame: pd.DataFrame, profiles: list[dict[str, Any]], options: dict[str, Any]
) -> list[str]:
    """Apply within-group redundancy checks and a declared MI-ranked size cap.

    Args:
        frame: Training-only estimator rows within the group's coverage.
        profiles: Eligible mutable decision records for one group.
        options: Fixed correlation limit, seed and group caps.

    Returns:
        Selected scalar names; protected nonconstant fields can exceed the cap.

    Notes:
        Updates each decision's training MI, status and reason.
    """
    scores = _mi_values(frame, profiles, options["seed"])
    numeric = [r["name"] for r in profiles if r["dtype"] != "category"]
    correlation = frame[numeric].corr(method="spearman").abs()
    ordered = sorted(
        profiles, key=lambda r: (not r["protected"], -scores[r["name"]], r["name"])
    )
    chosen: list[str] = []
    for row in ordered:
        name = row["name"]
        row["training_mi"] = scores[name]
        redundant = [
            old
            for old in chosen
            if old in numeric
            and name in numeric
            and correlation.loc[name, old] >= options["correlation_limit"]
        ]
        if redundant and not row["protected"]:
            row.update(
                status="excluded",
                reason="training_spearman_redundant_with:" + redundant[0],
            )
        elif (
            len(chosen) >= options["maximum_features"][row["group"]]
            and not row["protected"]
        ):
            row.update(status="excluded", reason="training_mi_rank_cap")
        else:
            chosen.append(name)
            row.update(
                status="selected",
                reason=(
                    "business_protected"
                    if row["protected"]
                    else "training_group_screen"
                ),
            )
    return chosen


def _cohort_evidence(
    frame: pd.DataFrame, profiles: list[dict[str, Any]], options: dict[str, Any]
) -> list[dict[str, Any]]:
    """Describe overlapping cohorts and estimate MI only with sufficient support.

    Args:
        frame: Fixed uniform training sample; no future-cutoff rows.
        profiles: All eligible feature decisions.
        options: Per-cohort row cap and minimum class support.

    Returns:
        Group-by-cohort MI and explicit unsupported statuses.
    """
    output = []
    masks = cohort_masks(frame)
    for cohort in ("low_activity", "high_activity", "new_observed"):
        part = frame.loc[masks[cohort]].head(options["cohort_rows"])
        for group in ("basic", "business", "sequence", "svd", "cooccurrence"):
            selected = [r for r in profiles if r["group"] == group and r["eligible"]]
            subset = part
            if group in {"svd", "cooccurrence"}:
                flag = (
                    "pair_svd_available" if group == "svd" else "pair_cooc_graph_known"
                )
                subset = part.loc[part[flag] == 1]
            positive = int(subset.target.sum())
            supported = (
                min(positive, len(subset) - positive)
                >= options["minimum_cohort_positives"]
            )
            output.append(
                {
                    "cohort": cohort,
                    "group": group,
                    "rows": len(subset),
                    "positives": positive,
                    "status": (
                        "estimated" if supported else "insufficient_class_support"
                    ),
                    "mi": (
                        _mi_values(subset, selected, options["seed"])
                        if supported
                        else {}
                    ),
                }
            )
    return output


def run_selection(settings: ValidationSettings) -> dict[str, Any]:
    """Fit all selection rules and preprocessing exclusively on the training cutoff.

    Args:
        settings: Confined inputs, immutable outputs and declared screening rules.

    Returns:
        Feature decisions, preprocessing contract and training-only support data.

    Raises:
        FileExistsError: A selection report already exists.
        ValueError: A source changed or a requested field violates the contract.
    """
    destination = settings.report_dir / "selection.json"
    if destination.exists():
        raise FileExistsError(destination)
    samples = verified_sample_manifest(settings)
    anchor = settings.options["splits"]["train"]
    snapshot = next(s for s in samples["snapshots"] if s["anchor"] == anchor)
    features = load_feature_settings(Path("configs/feature_system.json"))
    with feature_connection(features) as connection:
        connection.read_parquet(
            [str(PROJECT_ROOT / p["path"]) for p in snapshot["sample_parts"]]
        ).create_view("train")
        print("Profiling complete training rows", flush=True)
        profiles = training_profiles(connection, samples["definitions"])
        for row in profiles:
            row.update(group=feature_group(row), protected=business_protected(row))
            eligible, reason = _eligible_profile(row, settings.options)
            row.update(
                eligible=eligible,
                status="pending" if eligible else "excluded",
                reason=reason,
            )
        frame = connection.execute(
            "SELECT * FROM train ORDER BY hash(user_id,item_id,?) LIMIT ?",
            [settings.options["seed"], settings.options["selection_rows"]],
        ).df()
        require_contract(
            frame.target.nunique() == 2, "Training sample needs both classes"
        )
        groups = {}
        for group in settings.options["maximum_features"]:
            rows = [r for r in profiles if r["group"] == group and r["eligible"]]
            part = frame
            if group in {"svd", "cooccurrence"}:
                flag = (
                    "pair_svd_available" if group == "svd" else "pair_cooc_graph_known"
                )
                part = part.loc[part[flag] == 1]
            print("Screening group: " + group + ", rows=" + str(len(part)), flush=True)
            if rows and part.target.nunique() == 2:
                groups[group] = _select_group(part, rows, settings.options)
            else:
                groups[group] = []
                for row in rows:
                    row.update(
                        status="deferred", reason="insufficient_covered_class_support"
                    )
        cohort_evidence = _cohort_evidence(frame, profiles, settings.options)
        columns = [name for names in groups.values() for name in names]
        state = fit_transform_contract(connection, profiles, columns)
    result = {
        "status": "passed",
        "fit_anchor": anchor,
        "fit_split": "train",
        "training_rows": snapshot["rows"],
        "estimator_rows": len(frame),
        "estimator_positives": int(frame.target.sum()),
        "estimator_policy": (
            "uniform hash-ordered training pairs; no validation" + "/test rows"
        ),
        "group_candidates": dict(Counter(r["group"] for r in profiles)),
        "selected_groups": groups,
        "decisions": profiles,
        "cohort_evidence": cohort_evidence,
        "preprocessing": transform_record(state),
        "thresholds": settings.options,
    }
    write_json(destination, result)
    pd.DataFrame(
        [
            {
                k: r.get(k)
                for k in [
                    "name",
                    "group",
                    "protected",
                    "rows",
                    "missing_rate",
                    "variance",
                    "training_mi",
                    "status",
                    "reason",
                ]
            }
            for r in profiles
        ]
    ).to_csv(settings.report_dir / "feature_decisions.csv", index=False)
    return result
