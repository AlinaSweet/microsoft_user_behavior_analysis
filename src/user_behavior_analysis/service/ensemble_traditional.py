"""Score frozen traditional classifiers separately from the neural runtime."""

from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import xgboost
from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.dao.traditional_repository import load_temporal_plan
from user_behavior_analysis.dao.traditional_repository import load_traditional_bundle
from user_behavior_analysis.dao.traditional_repository import read_temporal_split
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.traditional_models import STACK_TRADITIONAL
from user_behavior_analysis.models.traditional_models import TemporalPlan
from user_behavior_analysis.service.traditional_tuning import predict_probability
from user_behavior_analysis.service.validation_metrics import explanation_rows
from user_behavior_analysis.service.wide_contracts import require_contract


def _replay(
    plan: TemporalPlan, catalog: dict[str, Any], scores: dict[str, np.ndarray]
) -> float:
    """Independently match all six published stage 3.2 probability columns.

    Args:
        plan: Exact chronological test candidates.
        catalog: Approved 3.2 held-out predictions.
        scores: Recomputed probabilities from the same trained bundles.

    Returns:
        Maximum absolute replay difference across all rows and columns.
    """
    recorded = pq.read_table(verify_registered_file(catalog["test_predictions"]))
    fields = ["as_of_time", "user_id", "item_id", "target"]
    expected = pq.read_table(
        verify_registered_file(plan.partitions["test"]["file"]), columns=fields
    )
    require_contract(
        recorded.select(fields).equals(expected), "Stage 3.2 test keys changed"
    )
    difference = max(
        float(np.max(np.abs(recorded[name].to_numpy() - values)))
        for name, values in scores.items()
    )
    require_contract(difference <= 5e-7, "Traditional test probability replay differs")
    return difference


def _explain_trees(models: dict[str, Any], cases: np.ndarray) -> dict[str, np.ndarray]:
    """Compute native exact TreeSHAP and independently check additive margins.

    Args:
        models: Trusted 3.2 frozen classifiers for the time backtest.
        cases: Standardized held-out rows for interpretation.

    Returns:
        XGBoost contribution matrix, bias error and standardized LR coefficients.
    """
    booster = models["xgboost_baseline"].get_booster()
    matrix = xgboost.DMatrix(cases, nthread=4)
    contribution = np.asarray(booster.predict(matrix, pred_contribs=True))
    margin = np.asarray(booster.predict(matrix, output_margin=True))
    error = np.max(np.abs(contribution.sum(axis=1) - margin))
    require_contract(error <= 5e-5, "TreeSHAP did not sum to the XGBoost raw margin")
    return {
        "xgb_shap": contribution[:, :-1],
        "xgb_shap_error": np.array(error),
        "lr_coefficient": np.asarray(models["logistic_regression_baseline"].coef_[0]),
        "lr_intercept": np.asarray(
            models["logistic_regression_baseline"].intercept_[0]
        ),
    }


def export_traditional_scores(
    sampling_catalog: Path,
    traditional_catalog: Path,
    split: str,
    output: Path,
    explanation: tuple[int, int],
) -> None:
    """Run vetted classifiers in a process without a loaded PyTorch runtime.

    Args:
        sampling_catalog: Approved temporal samples.
        traditional_catalog: Fingerprinted coefficients, trees and preprocessing.
        split: Validation or test, requested at the permitted stage.
        output: New local NPZ file for verified probabilities and aggregate inputs.
        explanation: Test explanation case count and sampling seed.
    """
    require_contract(split in {"validation", "test"}, "Unexpected scoring split")
    plan = load_temporal_plan(sampling_catalog)
    with threadpool_limits(limits=4):
        bundle, catalog = load_traditional_bundle(traditional_catalog, plan)
        data, _ = read_temporal_split(plan, split)
        values = bundle["preprocess"].transform(data.values)
        models = bundle["models"]
        names = tuple(models) if split == "test" else STACK_TRADITIONAL
        scores: dict[str, np.ndarray] = {
            name: predict_probability(models[name], values) for name in names
        }
        if split == "test":
            replay = _replay(plan, catalog, scores)
            cases = explanation_rows(data.target, *explanation)
            scores.update(_explain_trees(models, values[cases]))
            scores["replay_max_error"] = np.array(replay)
    with output.open("xb") as stream:
        np.savez_compressed(stream, allow_pickle=False, **scores)
