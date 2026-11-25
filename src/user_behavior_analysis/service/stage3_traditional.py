"""Run stage 3.2 on the same temporal samples, then score a frozen comparison."""

import json
from importlib.metadata import version
from pathlib import Path
from platform import machine
from platform import python_version
from platform import system
from time import perf_counter
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import optuna
import pandas as pd
import xgboost
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.traditional_repository import historical_transform
from user_behavior_analysis.dao.traditional_repository import load_temporal_plan
from user_behavior_analysis.dao.traditional_repository import read_temporal_split
from user_behavior_analysis.dao.traditional_repository import write_test_predictions
from user_behavior_analysis.models.traditional_models import MODEL_FAMILIES
from user_behavior_analysis.models.traditional_models import LabeledMatrix
from user_behavior_analysis.models.traditional_models import TraditionalSettings
from user_behavior_analysis.service.traditional_tuning import FamilyFit
from user_behavior_analysis.service.traditional_tuning import predict_probability
from user_behavior_analysis.service.traditional_tuning import tune_family
from user_behavior_analysis.service.validation_metrics import probability_metrics
from user_behavior_analysis.service.validation_metrics import validation_f1_threshold
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import require_contract


def _freeze_selection(
    fits: dict[str, FamilyFit], validation: LabeledMatrix
) -> dict[str, Any]:
    """Freeze family, parameters and thresholds using only natural validation rows.

    Args:
        fits: Baseline and tuned fits from each model family.
        validation: Complete chronological validation rows and labels.

    Returns:
        Model decision record and baseline/tuned validation metrics.
    """
    models = {}
    for family, current in fits.items():
        for variant, candidate in (
            ("baseline", current.baseline),
            ("tuned", current.tuned),
        ):
            start = perf_counter()
            scores = predict_probability(candidate.estimator, validation.values)
            seconds = perf_counter() - start
            threshold = validation_f1_threshold(validation.target, scores)
            metrics = probability_metrics(validation.target, scores, threshold)
            require_contract(
                metrics["roc_auc"] == candidate.validation_auc,
                "Validation scores changed after optimization",
            )
            models[family + "_" + variant] = {
                "family": family,
                "variant": variant,
                "trial": candidate.trial,
                "parameters": candidate.parameters,
                "fit_seconds": candidate.fit_seconds,
                "rss_after_fit_bytes": candidate.rss_after_fit_bytes,
                "score_seconds": seconds,
                "metrics": metrics,
            }
    maximum_auc = max(current.tuned.validation_auc for current in fits.values())
    chosen = next(
        family
        for family in MODEL_FAMILIES
        if fits[family].tuned.validation_auc == maximum_auc
    )
    return {
        "frozen_at_utc": utc_timestamp(),
        "chosen_family": chosen,
        "selection": "Highest tuned validation ROC-AUC. Family order resolves ties.",
        "threshold_rule": "Maximum validation F1. Highest threshold resolves ties.",
        "models": models,
    }


def _save_models(
    path: Path,
    fits: dict[str, FamilyFit],
    preprocess: Pipeline,
    features: tuple[str, ...],
) -> None:
    """Persist the already fitted preprocessing and six models before test access.

    Args:
        path: New local model bundle path.
        fits: Frozen baseline and tuned models.
        preprocess: Transform fitted once on the chronological training set.
        features: Approved model input ordering.
    """
    models = {}
    for family, current in fits.items():
        models[family + "_baseline"] = current.baseline.estimator
        models[family + "_tuned"] = current.tuned.estimator
    with path.open("xb") as stream:
        joblib.dump(
            {"features": features, "preprocess": preprocess, "models": models},
            stream,
            compress=3,
        )


def _score_test(
    bundle: dict[str, Any], test: LabeledMatrix, frozen: dict[str, Any]
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    """Apply the frozen model bundle and thresholds to complete natural test rows.

    Args:
        bundle: Previously saved and reloaded training-state bundle.
        test: Untouched chronological test matrix and labels.
        frozen: Validation-only choices and metrics.

    Returns:
        Aligned test probabilities and combined validation/test comparison rows.
    """
    features = bundle["preprocess"].transform(test.values)
    all_scores = {}
    rows = []
    for name, record in frozen["models"].items():
        common = {
            "family": record["family"],
            "variant": record["variant"],
            "trial": record["trial"],
            "fit_seconds": record["fit_seconds"],
            "rss_after_fit_bytes": record["rss_after_fit_bytes"],
        }
        rows.append(
            dict(
                common,
                split="validation",
                score_seconds=record["score_seconds"],
                **record["metrics"],
            )
        )
        start = perf_counter()
        scores = predict_probability(bundle["models"][name], features)
        seconds = perf_counter() - start
        all_scores[name] = scores
        metrics = probability_metrics(
            test.target, scores, record["metrics"]["threshold"]
        )
        rows.append(dict(common, split="test", score_seconds=seconds, **metrics))
    return all_scores, rows


def _write_comparison(
    settings: TraditionalSettings,
    fits: dict[str, FamilyFit],
    rows: list[dict[str, Any]],
) -> None:
    """Save aggregate baseline/tuned scores and every sampled model parameter.

    Args:
        settings: Confined report destination.
        fits: Complete sequential Optuna traces.
        rows: Full validation and test metrics with fixed thresholds.
    """
    with (settings.report_dir / "model_comparison.csv").open(
        "x", encoding="utf-8", newline=""
    ) as stream:
        pd.DataFrame(rows).to_csv(stream, index=False, lineterminator="\n")
    trials = [
        dict(trial, parameters=json.dumps(trial["parameters"], sort_keys=True))
        for fit in fits.values()
        for trial in fit.trials
    ]
    with (settings.report_dir / "optuna_trials.csv").open(
        "x", encoding="utf-8", newline=""
    ) as stream:
        pd.DataFrame(trials).to_csv(stream, index=False, lineterminator="\n")


def run_traditional_models(settings: TraditionalSettings) -> dict[str, Any]:
    """Tune the three classifiers on validation and publish audited test outputs.

    Args:
        settings: Checked source, run version and computational budget.

    Returns:
        Catalog of model, prediction and report fingerprints.

    Raises:
        FileExistsError: A requested output version already exists.
    """
    for path in (settings.data_root, settings.report_dir, settings.catalog):
        if path.exists():
            raise FileExistsError(f"Choose an unused model output version: {path}")
    start = perf_counter()
    plan = load_temporal_plan(settings.sampling_catalog)
    train, train_history = read_temporal_split(plan, "train")
    validation, validation_history = read_temporal_split(plan, "validation")
    settings.data_root.mkdir(parents=True)
    settings.report_dir.mkdir(parents=True)
    preprocess = historical_transform()
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    with threadpool_limits(limits=settings.threads):
        train = LabeledMatrix(preprocess.fit_transform(train.values), train.target)
        validation = LabeledMatrix(
            preprocess.transform(validation.values), validation.target
        )
        require_contract(
            int(preprocess.named_steps["scale"].n_samples_seen_)
            == train_history["rows"],
            "Transform did not fit the exact training rows",
        )
        fits = {
            family: tune_family(family, train, validation, settings)
            for family in MODEL_FAMILIES
        }
        frozen = _freeze_selection(fits, validation)
        choice_path = settings.report_dir / "validation_selection.json"
        write_json(choice_path, frozen)
        model_path = settings.data_root / "traditional_models.joblib"
        _save_models(model_path, fits, preprocess, plan.features)
        bundle = joblib.load(model_path)
        require_contract(
            tuple(bundle["features"]) == plan.features, "Model schema changed"
        )
        del train, validation
        print(
            "Froze validation decisions and models. Reading chronological test rows.",
            flush=True,
        )
        test, test_history = read_temporal_split(plan, "test")
        predictions, rows = _score_test(bundle, test, frozen)
    prediction_record = write_test_predictions(
        plan.partitions["test"],
        predictions,
        settings.data_root / "test_predictions.parquet",
    )
    _write_comparison(settings, fits, rows)
    audit = {
        "status": "passed",
        "source_sampling_catalog": plan.source,
        "protocol": "time_backtest",
        "features": list(plan.features),
        "partitions": {
            "train": train_history,
            "validation": validation_history,
            "test": test_history,
        },
        "objective": "Optuna TPE maximizes validation ROC-AUC",
        "trials_per_model_including_baseline": settings.trials_per_model,
        "seed": settings.seed,
        "threads": settings.threads,
        "frozen_selection": file_record(choice_path),
        "test_predictions_read_back": prediction_record["rows"],
        "elapsed_seconds": perf_counter() - start,
        "runtime": {
            "system": system(),
            "machine": machine(),
            "python": python_version(),
            "xgboost": xgboost.__version__,
            **{
                name: version(name)
                for name in ("lightgbm", "optuna", "scikit-learn", "numpy")
            },
        },
    }
    write_json(settings.report_dir / "audit.json", audit)
    catalog = {
        "kind": "stage3_traditional_models",
        "status": "passed",
        "protocol": "time_backtest",
        "source_sampling_catalog": plan.source,
        "chosen_family": frozen["chosen_family"],
        "models": file_record(model_path),
        "test_predictions": prediction_record,
        "reports": [
            file_record(settings.report_dir / name)
            for name in (
                "audit.json",
                "model_comparison.csv",
                "optuna_trials.csv",
                "validation_selection.json",
            )
        ],
    }
    settings.catalog.parent.mkdir(parents=True, exist_ok=True)
    with settings.catalog.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(catalog, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return catalog
