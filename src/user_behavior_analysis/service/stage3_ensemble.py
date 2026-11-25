"""Fit leakage-controlled stacking and publish quantitative error analyses."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import torch
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.sequence_repository import encode_split
from user_behavior_analysis.dao.sequence_repository import read_sequence_source
from user_behavior_analysis.dao.traditional_repository import load_temporal_plan
from user_behavior_analysis.dao.traditional_repository import write_test_predictions
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.sequence_models import AdvancedSettings
from user_behavior_analysis.models.sequence_models import SequenceSplit
from user_behavior_analysis.models.traditional_models import STACK_TRADITIONAL
from user_behavior_analysis.service.ensemble_diagnostics import error_profiles
from user_behavior_analysis.service.ensemble_diagnostics import slice_metrics
from user_behavior_analysis.service.ensemble_diagnostics import split_meta_validation
from user_behavior_analysis.service.ensemble_diagnostics import test_context
from user_behavior_analysis.service.ensemble_explanations import din_shap
from user_behavior_analysis.service.ensemble_explanations import publish_attributions
from user_behavior_analysis.service.sequence_networks import PurchaseNetwork
from user_behavior_analysis.service.sequence_training import probabilities
from user_behavior_analysis.service.stage3_deep import prepare_outputs
from user_behavior_analysis.service.stage3_deep import restore_network
from user_behavior_analysis.service.stage3_deep import write_csv
from user_behavior_analysis.service.validation_metrics import clustered_auc_deltas
from user_behavior_analysis.service.validation_metrics import explanation_rows
from user_behavior_analysis.service.validation_metrics import probability_metrics
from user_behavior_analysis.service.validation_metrics import validation_f1_threshold
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import require_contract

_MEMBERS = (*STACK_TRADITIONAL, "din_train_only")
_CANDIDATES = (*_MEMBERS, "soft_vote", "stacking")


def _tree_scores(settings: AdvancedSettings, split: str) -> dict[str, np.ndarray]:
    """Replay the exact 3.2 baselines in a separate conventional model process.

    Args:
        settings: Vetted input catalogs and this stage's local binary directory.
        split: Validation during fitting, or test only after final selection.

    Returns:
        Score arrays in immutable candidate order and optional post-test explanations.
    """
    with tempfile.TemporaryDirectory(dir=settings.ensemble.data_root) as directory:
        out = Path(directory) / "base_scores.npz"
        subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/score_stage3_traditional.py"),
                str(settings.sampling_catalog),
                str(settings.traditional_catalog),
                split,
                str(out),
                str(settings.budget["shap_cases"]),
                str(settings.budget["seed"] + 4),
            ],
            cwd=PROJECT_ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(PROJECT_ROOT / "src"),
                "PYTHONUTF8": "1",
            },
            check=True,
        )
        with np.load(out, allow_pickle=False) as archive:
            return {name: archive[name] for name in archive.files}


def _meta_input(base: dict[str, np.ndarray]) -> np.ndarray:
    """Convert the same three frozen base probabilities to log-odds features.

    Args:
        base: Aligned probability vectors for the three named stacking members.

    Returns:
        Three clipped finite log-odds columns in an immutable model order.
    """
    values = np.column_stack([base[name] for name in _MEMBERS]).astype(np.float64)
    clipped = np.clip(values, 1e-7, 1 - 1e-7)
    return np.log(clipped / (1 - clipped))


def _scores(model: Pipeline, base: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Evaluate the base learners, fixed soft vote and fitted meta classifier.

    Args:
        model: Train-fitted logistic stacking pipeline.
        base: Three aligned base probability vectors.

    Returns:
        Five aligned model probability columns.
    """
    return {
        **{name: base[name] for name in _MEMBERS},
        "soft_vote": np.mean([base[name] for name in _MEMBERS], axis=0),
        "stacking": np.asarray(model.predict_proba(_meta_input(base))[:, 1]),
    }


def _fit_stack(
    split: SequenceSplit, base: dict[str, np.ndarray], seed: int
) -> tuple[Pipeline, dict[str, Any]]:
    """Fit the meta layer on one validation user group and freeze on the other.

    Args:
        split: Original chronological validation partition.
        base: Predictions from models fitted before validation was opened.
        seed: Predeclared validation group-assignment seed.

    Returns:
        Meta classifier and fixed decision records for the five candidates.
    """
    fit = split_meta_validation(split.keys, seed)
    labels = split.target
    require_contract(
        len(np.unique(labels[fit])) == len(np.unique(labels[~fit])) == 2,
        "Meta-fit and decision groups must both contain each class",
    )
    estimator = Pipeline(
        [
            ("scale", StandardScaler()),
            ("logistic", LogisticRegression(C=1.0, max_iter=600, random_state=seed)),
        ]
    )
    with threadpool_limits(limits=4, user_api="blas"):
        estimator.fit(_meta_input(base)[fit], labels[fit])
        decision = _scores(estimator, {name: base[name][~fit] for name in _MEMBERS})
    validation = {
        name: probability_metrics(
            labels[~fit], value, validation_f1_threshold(labels[~fit], value)
        )
        for name, value in decision.items()
    }
    fitting, checking = split.keys.loc[fit, "user_id"], split.keys.loc[~fit, "user_id"]
    overlap = len(set(fitting).intersection(checking))
    require_contract(overlap == 0, "Meta-fit and threshold decision users overlap")
    frozen = {
        "frozen_at_utc": utc_timestamp(),
        "members": list(_MEMBERS),
        "base_training_only": True,
        "meta_fit": {
            "users": int(fitting.nunique()),
            "rows": int(fit.sum()),
            "positives": int(labels[fit].sum()),
        },
        "decision": {
            "users": int(checking.nunique()),
            "rows": int((~fit).sum()),
            "positives": int(labels[~fit].sum()),
        },
        "validation_user_overlap": overlap,
        "meta_coefficients": estimator.named_steps["logistic"].coef_[0].tolist(),
        "best_individual": max(_MEMBERS, key=lambda name: validation[name]["roc_auc"]),
        "best_candidate": max(
            _CANDIDATES, key=lambda name: validation[name]["roc_auc"]
        ),
        "validation": validation,
    }
    return estimator, frozen


def _explain(
    settings: AdvancedSettings,
    network: PurchaseNetwork,
    splits: tuple[SequenceSplit, SequenceSplit],
    features: tuple[str, ...],
    conventional: dict[str, np.ndarray],
) -> dict[str, Any]:
    """Generate coefficient and audited SHAP summaries on fixed reference samples.

    Args:
        settings: Experiment budget and small-report destination.
        network: The training-only DIN used by the ensemble.
        splits: Natural train and test partitions in that order.
        features: Verified model input definition.
        conventional: Native TreeSHAP and LR coefficients from the CPU worker.

    Returns:
        Explanation sample support and additive recovery audits.
    """
    train, test = splits
    budget = settings.budget
    output = settings.ensemble.report_dir
    cases = explanation_rows(test.target, budget["shap_cases"], budget["seed"] + 4)
    backgrounds = np.random.default_rng(budget["seed"] + 5).choice(
        len(train.target),
        min(budget["shap_background"], len(train.target)),
        replace=False,
    )
    names, values, error = din_shap(
        network,
        test.batch(torch.from_numpy(cases)),
        train.batch(torch.from_numpy(backgrounds)),
        features,
    )
    publish_attributions(output, "din_shap", "DIN grouped SHAP", names, values)
    publish_attributions(
        output,
        "xgboost_shap",
        "XGBoost TreeSHAP",
        list(features),
        conventional["xgb_shap"],
    )
    coefficients: list[dict[str, Any]] = [
        {
            "feature": name,
            "coefficient": float(coef),
            "odds_ratio_per_sd": float(np.exp(coef)),
        }
        for name, coef in zip(features, conventional["lr_coefficient"], strict=True)
    ]
    coefficients.sort(key=lambda item: abs(item["coefficient"]), reverse=True)
    write_csv(output / "logistic_coefficients.csv", coefficients)
    return {
        "cases": len(cases),
        "case_positives": int(test.target[cases].sum()),
        "background_rows_from_train": len(backgrounds),
        "din_groups": names,
        "din_additivity_max_error": error,
        "xgb_additivity_max_error": float(conventional["xgb_shap_error"]),
        "logistic_intercept": float(conventional["lr_intercept"]),
    }


def _read_deep(settings: AdvancedSettings) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify that a DIN checkpoint was fixed without validation labels.

    Args:
        settings: Paths to the completed deep experiment and its inputs.

    Returns:
        Checked catalog and trusted tensor-only checkpoint.
    """
    deep = read_json_object(settings.deep.catalog)
    require_contract(
        deep.get("status") == "passed"
        and deep.get("kind") == "stage3_deep_models"
        and deep.get("source_sampling_catalog")
        == file_record(settings.sampling_catalog)
        and deep.get("feature_catalog") == file_record(settings.feature_catalog)
        and deep.get("traditional_catalog") == file_record(settings.traditional_catalog)
        and deep["stack_plan"]["validation_used"] is False,
        "Need a matching 3.3 catalog with the training-only DIN checkpoint",
    )
    row = next(item for item in deep["reports"] if item["path"].endswith("/audit.json"))
    audit = read_json_object(verify_registered_file(row))
    require_contract(
        audit["budget"]["sequence_length"] == settings.budget["sequence_length"],
        "Stacking sequence length differs from the fitted DIN",
    )
    frozen = torch.load(
        verify_registered_file(deep["stack_member"]),
        map_location="cpu",
        weights_only=True,
    )
    return deep, frozen


def _holdout_diagnostics(
    settings: AdvancedSettings,
    splits: tuple[SequenceSplit, SequenceSplit],
    predictions: dict[str, np.ndarray],
    frozen: dict[str, Any],
    features: tuple[str, ...],
) -> dict[str, Any]:
    """Compare frozen predictions and summarize observed errors with support.

    Args:
        settings: Aggregate output paths and bootstrap budget.
        splits: Natural training and test rows in that order.
        predictions: Complete test probabilities in candidate order.
        frozen: Decisions made on the user-disjoint validation holdout.
        features: Historical dense column names.

    Returns:
        Paired AUC difference and uncertainty versus the validation-selected base.
    """
    train, test = splits
    output = settings.ensemble.report_dir
    thresholds = {name: frozen["validation"][name]["threshold"] for name in _CANDIDATES}
    rows = [
        dict(frozen["validation"][name], model=name, split="validation_decision")
        for name in _CANDIDATES
    ] + [
        dict(
            probability_metrics(test.target, value, thresholds[name]),
            model=name,
            split="test",
        )
        for name, value in predictions.items()
    ]
    write_csv(output / "model_comparison.csv", rows)
    context = test_context(train, test)
    write_csv(
        output / "slice_metrics.csv",
        slice_metrics(test.target, predictions, thresholds, context),
    )
    diagnostic_models = ("xgboost_baseline", "din_train_only", "stacking")
    write_csv(
        output / "error_profiles.csv",
        error_profiles(
            test,
            {key: predictions[key] for key in diagnostic_models},
            thresholds,
            features,
            context,
        ),
    )
    reference = frozen["best_individual"]
    difference = clustered_auc_deltas(
        test.target,
        {"business": predictions[reference], "stacking": predictions["stacking"]},
        np.unique(test.keys["user_id"].to_numpy(), return_inverse=True)[1],
        settings.budget["bootstrap_repeats"],
        settings.budget["seed"] + 3,
    )["stacking"]
    return {**difference, "reference": reference}


def run_ensemble(settings: AdvancedSettings) -> dict[str, Any]:
    """Train stage 3.4 and evaluate its frozen probabilities and explanations.

    Args:
        settings: Validated sources and new output paths.

    Returns:
        Artifact catalog bound to the exact prior stages and test partition.
    """
    paths, budget = settings.ensemble, settings.budget
    torch.set_num_threads(budget["threads"])
    plan = load_temporal_plan(settings.sampling_catalog)
    deep, checkpoint = _read_deep(settings)
    require_contract(
        deep["stack_plan"]["training_anchor"] == plan.anchors["train"],
        "DIN stack member was fitted at a different cutoff",
    )
    preprocess = joblib.load(verify_registered_file(deep["preprocess"]))
    vocab, weights = checkpoint["vocabulary"], checkpoint["model"]
    network = restore_network(weights, vocab, len(plan.features))
    prepare_outputs(paths)
    train, validation = (
        encode_split(
            read_sequence_source(plan, settings.feature_catalog, split),
            vocab,
            preprocess,
            budget["sequence_length"],
        )
        for split in ("train", "validation")
    )
    base = _tree_scores(settings, "validation")
    base["din_train_only"] = probabilities(
        network, validation, budget["batch_rows"], weights["offset"]
    )
    estimator, frozen = _fit_stack(validation, base, budget["seed"] + 2)
    model_path = paths.data_root / "stacking.joblib"
    with model_path.open("xb") as stream:
        joblib.dump(estimator, stream)
    write_json(paths.report_dir / "validation_selection.json", frozen)
    print("Stacking decisions frozen. Reading test rows.", flush=True)
    del validation, base
    test = encode_split(
        read_sequence_source(plan, settings.feature_catalog, "test"),
        vocab,
        preprocess,
        budget["sequence_length"],
    )
    conventional = _tree_scores(settings, "test")
    conventional["din_train_only"] = probabilities(
        network, test, budget["batch_rows"], weights["offset"]
    )
    predictions = _scores(joblib.load(model_path), conventional)
    write_json(
        paths.report_dir / "audit.json",
        {
            "status": "passed",
            "time_anchors": plan.anchors,
            "test_rows": len(test.target),
            "traditional_replay_max_error": float(conventional["replay_max_error"]),
            "meta_validation_user_overlap": frozen["validation_user_overlap"],
            "auc_user_cluster_bootstrap": _holdout_diagnostics(
                settings, (train, test), predictions, frozen, plan.features
            ),
            "explanation": _explain(
                settings, network, (train, test), plan.features, conventional
            ),
        },
    )
    final = write_test_predictions(
        plan.partitions["test"],
        predictions,
        paths.data_root / "test_predictions.parquet",
    )
    catalog = {
        "kind": "stage3_ensemble",
        "status": "passed",
        "source_sampling_catalog": plan.source,
        "source_deep_catalog": file_record(settings.deep.catalog),
        "source_traditional_catalog": file_record(settings.traditional_catalog),
        "meta_model": file_record(model_path),
        "chosen_on_validation": frozen["best_candidate"],
        "test_predictions": final,
        "reports": [file_record(p) for p in sorted(paths.report_dir.iterdir())],
    }
    write_json(paths.catalog, catalog)
    return catalog
