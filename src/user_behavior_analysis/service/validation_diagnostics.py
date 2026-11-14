"""Audit frozen selections and recover full-training cohort support explicitly."""

from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
from scipy import special  # type: ignore[import-untyped]

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.dao.validation_repository import iter_sample_frames
from user_behavior_analysis.dao.validation_repository import verified_sample_manifest
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.validation_models import ValidationSettings
from user_behavior_analysis.service.validation_experiments import _apply_fallback
from user_behavior_analysis.service.validation_preprocessing import transform_frame
from user_behavior_analysis.service.validation_selection import _mi_values
from user_behavior_analysis.service.wide_contracts import require_contract


def audit_training_groups(settings: ValidationSettings) -> dict[str, Any]:
    """Check cross-group redundancy and sample rare cohorts from full train only.

    Args:
        settings: Fixed split and estimator configuration.

    Returns:
        Exact population supports, conditional MI and cross-group redundancy.

    Notes:
        This diagnostic does not change frozen selections or experiment parameters.
    """
    manifest = verified_sample_manifest(settings)
    selected = read_json_object(settings.report_dir / "selection.json")
    snapshot = next(
        s
        for s in manifest["snapshots"]
        if s["anchor"] == settings.options["splits"]["train"]
    )
    decisions = [r for r in selected["decisions"] if r["status"] == "selected"]
    cohorts = {
        "low_activity": "user_activity_level_7d=0",
        "high_activity": "user_activity_level_7d>=2",
        "new_observed": "user_observed_age_days<=3",
    }
    output = []
    with feature_connection(
        load_feature_settings(Path("configs/feature_system.json"))
    ) as connection:
        connection.read_parquet(
            [str(PROJECT_ROOT / p["path"]) for p in snapshot["sample_parts"]]
        ).create_view("train")
        for cohort, condition in cohorts.items():
            for group in ("basic", "business", "sequence", "svd", "cooccurrence"):
                where = condition
                if group in {"svd", "cooccurrence"}:
                    where += " AND " + (
                        "pair_svd_available=1"
                        if group == "svd"
                        else "pair_cooc_graph_known=1"
                    )
                count = require_result_row(
                    connection.execute(
                        "SELECT COUNT(*),SUM(target) FROM train WHERE " + where
                    ).fetchone()
                )
                frame = connection.execute(
                    "SELECT * FROM train WHERE "
                    + where
                    + " ORDER BY hash(user_id,item_id,?) LIMIT ?",
                    [settings.options["seed"], settings.options["cohort_rows"]],
                ).df()
                positives = int(frame.target.sum())
                supported = (
                    min(positives, len(frame) - positives)
                    >= settings.options["minimum_cohort_positives"]
                )
                definitions = [r for r in decisions if r["group"] == group]
                output.append(
                    {
                        "cohort": cohort,
                        "group": group,
                        "population_rows": count[0],
                        "population_positives": count[1],
                        "estimator_rows": len(frame),
                        "estimator_positives": positives,
                        "status": (
                            "estimated" if supported else "insufficient_class_support"
                        ),
                        "mi": (
                            _mi_values(frame, definitions, settings.options["seed"])
                            if supported
                            else {}
                        ),
                    }
                )
        frame = connection.execute(
            ("SELECT * FROM train ORDER BY hash(user_id,ite" + "m_id,?) LIMIT ?"),
            [settings.options["seed"], settings.options["selection_rows"]],
        ).df()
    numeric = [r for r in decisions if r["dtype"] != "category"]
    correlation = frame[[r["name"] for r in numeric]].corr(method="spearman")
    redundant = []
    for index, left in enumerate(numeric):
        for right in numeric[index + 1 :]:
            if left["group"] == right["group"]:
                continue
            value = correlation.loc[left["name"], right["name"]]
            if abs(value) >= settings.options["correlation_limit"]:
                redundant.append(
                    {
                        "left": left["name"],
                        "right": right["name"],
                        "spearman": float(value),
                        "action": "retained_for_predeclared_group_ablation",
                        "protected_business": left["protected"] or right["protected"],
                    }
                )
    result = {
        "status": "passed",
        "fit_split": "train",
        "cohorts_overlap": True,
        "cohort_estimator_policy": (
            "uniform sample within each full-training coho"
            + "rt; no future cutoff rows"
        ),
        "cohorts": output,
        "cross_group_high_correlations": redundant,
        "changes_to_selection": False,
    }
    write_json(settings.report_dir / "training_group_diagnostics.json", result)
    return result


def audit_prediction_replay(settings: ValidationSettings) -> dict[str, Any]:
    """Recompute every probability directly from persisted linear coefficients.

    Args:
        settings: Existing immutable sample and experiment output paths.

    Returns:
        All-row probability, row order and training-visit audit evidence.

    Raises:
        ValueError: Saved predictions differ or a model visited the wrong rows.

    Notes:
        Reads only this project's newly created model artifact, never user uploads.
    """
    manifest = verified_sample_manifest(settings)
    experiments = read_json_object(settings.report_dir / "experiments.json")
    model_path = verify_registered_file(experiments["model_file"])
    fitted = joblib.load(model_path)
    state, indices, models = (
        fitted["preprocessing"],
        fitted["indices"],
        fitted["models"],
    )
    snapshots = {s["anchor"]: s for s in manifest["snapshots"]}
    expected = snapshots[settings.options["splits"]["train"]]["rows"]
    require_contract(
        experiments["training"]["rows_per_epoch_per_model"]
        == [expected] * settings.options["epochs"],
        "Incomplete training visit",
    )
    results = []
    for split in ("validation", "test"):
        anchor = settings.options["splits"][split]
        score = pd.read_parquet(
            settings.sample_root / "predictions" / (anchor + ".parquet")
        )
        columns = list(
            dict.fromkeys(
                state.columns
                + [
                    "user_id",
                    "item_id",
                    "target",
                    "pair_svd_available",
                    "pair_cooc_graph_known",
                ]
            )
        )
        offset, maximum = 0, 0.0
        for frame in iter_sample_frames(
            snapshots[anchor]["sample_parts"], columns, settings.options["batch_rows"]
        ):
            matrix = transform_frame(frame, state)
            probabilities = {
                # SciPy exposes this tested public ufunc through a compiled module.
                name: special.expit(  # pylint: disable=no-member
                    np.asarray(matrix[:, indices[name]] @ model.coef_.ravel()).ravel()
                    + model.intercept_[0]
                )
                for name, model in models.items()
            }
            _apply_fallback(probabilities, frame)
            saved = score.iloc[offset : offset + len(frame)]
            require_contract(
                np.array_equal(
                    frame[["user_id", "item_id", "target"]].to_numpy(),
                    saved[["user_id", "item_id", "target"]].to_numpy(),
                ),
                "Prediction order/labels differ",
            )
            for name, values in probabilities.items():
                maximum = max(
                    maximum, float(np.max(np.abs(values - saved[name].to_numpy())))
                )
            offset += len(frame)
        require_contract(
            offset == len(score) and maximum < 1e-10, "Coefficient replay differs"
        )
        results.append(
            {"split": split, "rows": offset, "maximum_probability_difference": maximum}
        )
    result = {
        "status": "passed",
        "all_models_replayed": len(models),
        "snapshots": results,
        "training_rows_per_model_per_epoch": expected,
    }
    write_json(settings.report_dir / "prediction_replay.json", result)
    return result
