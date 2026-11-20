"""Run the published sample protocols and evaluate fixed imbalance comparisons."""

import csv
import json
import time
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from platform import machine
from platform import python_version
from platform import system
from typing import Any

import joblib  # type: ignore[import-untyped]
import psutil
from sklearn.impute import SimpleImputer  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.sampling_repository import build_partitions
from user_behavior_analysis.dao.sampling_repository import load_partition
from user_behavior_analysis.dao.validation_repository import verified_sample_manifest
from user_behavior_analysis.models.sampling_models import PartitionEvidence
from user_behavior_analysis.models.sampling_models import SamplingSettings
from user_behavior_analysis.service.sampling_strategies import STRATEGIES
from user_behavior_analysis.service.sampling_strategies import prepare_training
from user_behavior_analysis.service.validation_metrics import probability_metrics
from user_behavior_analysis.service.validation_metrics import validation_f1_threshold
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import require_contract

_MAX_ITER = 300


@dataclass(frozen=True)
class ProtocolFit:
    """Train-fitted preprocessing and validation evidence for one split protocol.

    Attributes:
        preprocess: Imputer and scaler independently fitted on this training part.
        models: Fixed logistic comparison models by treatment.
        treatments: Actual fitted row, weight and resource accounting.
        validation: Same-row validation scores summarized by treatment.
    """

    preprocess: Pipeline
    models: dict[str, LogisticRegression]
    treatments: dict[str, dict[str, Any]]
    validation: dict[str, dict[str, Any]]


def _fit_protocol(
    settings: SamplingSettings, dataset: dict[str, PartitionEvidence]
) -> ProtocolFit:
    """Fit all strategies and compute validation metrics without accessing test data.

    Args:
        settings: Frozen ratio, seed and continuous feature choices.
        dataset: Audited natural split artifacts for this protocol.

    Returns:
        Fitted preprocessing/models and full validation evidence.
    """
    train, train_target = load_partition(dataset["train"], settings.features)
    valid, valid_target = load_partition(dataset["validation"], settings.features)
    preprocess = Pipeline(
        [
            ("median", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
        ]
    )
    training = preprocess.fit_transform(train)
    validation = preprocess.transform(valid)
    del train, valid
    models: dict[str, LogisticRegression] = {}
    treatments: dict[str, dict[str, Any]] = {}
    scores: dict[str, dict[str, Any]] = {}
    for strategy in STRATEGIES:
        started = time.monotonic()
        training_variant = prepare_training(strategy, training, train_target, settings)
        model = LogisticRegression(
            C=1.0,
            solver="lbfgs",
            max_iter=_MAX_ITER,
            tol=0.0001,
            class_weight=training_variant.weights,
        )
        model.fit(training_variant.values, training_variant.target)
        iterations = int(model.n_iter_.max())
        require_contract(iterations < _MAX_ITER, "Logistic fit limit: " + strategy)
        positives = int(training_variant.target.sum())
        negatives = len(training_variant.target) - positives
        weight_zero = training_variant.weights[0]
        weight_one = training_variant.weights[1]
        treatments[strategy] = {
            "fit_rows": len(training_variant.target),
            "fit_positives": positives,
            "fit_negatives": negatives,
            "synthetic_positives": training_variant.synthetic_rows,
            "positive_weight": weight_one,
            "negative_weight": weight_zero,
            "effective_positive_rate": (
                positives
                * weight_one
                / (positives * weight_one + negatives * weight_zero)
            ),
            "fit_seconds": round(time.monotonic() - started, 6),
            "fit_iterations": iterations,
            "rss_after_fit_bytes": psutil.Process().memory_info().rss,
        }
        del training_variant
        models[strategy] = model
        probabilities = model.predict_proba(validation)[:, 1]
        scores[strategy] = probability_metrics(
            valid_target,
            probabilities,
            validation_f1_threshold(valid_target, probabilities),
        )
        print(
            f"Validated {strategy}: AP={scores[strategy]['average_precision']:.6f}",
            flush=True,
        )
    return ProtocolFit(preprocess, models, treatments, scores)


def _freeze_selection(fits: dict[str, ProtocolFit]) -> dict[str, Any]:
    """Record validation-only strategy selection and thresholds for each protocol.

    Args:
        fits: Completed validation comparisons.

    Returns:
        Timestamped selections, frozen thresholds and validation probabilities metrics.
    """
    protocols = {}
    for name, fit in fits.items():
        average_precision = {
            strategy: float(fit.validation[strategy]["average_precision"])
            for strategy in STRATEGIES
        }
        best_score = max(average_precision.values())
        chosen_strategy = next(
            strategy
            for strategy, score in average_precision.items()
            if score == best_score
        )
        protocols[name] = {
            "chosen_strategy": chosen_strategy,
            "thresholds": {
                key: value["threshold"] for key, value in fit.validation.items()
            },
        }
    return {
        "frozen_at_utc": utc_timestamp(),
        "selection_metric": "validation average_precision; strategy order breaks ties",
        "threshold_rule": "maximum validation F1; highest threshold breaks ties",
        "protocols": protocols,
    }


def _score_test(
    settings: SamplingSettings,
    dataset: dict[str, PartitionEvidence],
    fit: ProtocolFit,
    thresholds: dict[str, float],
) -> dict[str, dict[str, Any]]:
    """Score the untouched test split after validation decisions have been saved.

    Args:
        settings: Continuous input schema.
        dataset: Natural split artifacts for this protocol.
        fit: Frozen training-only preprocessing and fitted models.
        thresholds: Already recorded validation thresholds.

    Returns:
        Same-row test metrics for every predeclared strategy.
    """
    test, target = load_partition(dataset["test"], settings.features)
    values = fit.preprocess.transform(test)
    return {
        strategy: probability_metrics(
            target, model.predict_proba(values)[:, 1], thresholds[strategy]
        )
        for strategy, model in fit.models.items()
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    """Write an ordered aggregate CSV using the supplied column order.

    Args:
        path: Destination in the new report directory.
        rows: Data rows sharing the same named columns.
    """
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_reports(
    settings: SamplingSettings,
    datasets: dict[str, dict[str, PartitionEvidence]],
    fits: dict[str, ProtocolFit],
    tests: dict[str, dict[str, dict[str, Any]]],
    audit: dict[str, Any],
) -> None:
    """Save reproducible partition summaries, metrics and independent audit evidence.

    Args:
        settings: New output version paths.
        datasets: Physical partition metadata from both protocols.
        fits: Frozen validation and training accounting for each protocol.
        tests: Held-out test metrics for each protocol.
        audit: Independent label, window and partition coverage controls.
    """
    splits = []
    results = []
    for name, dataset in datasets.items():
        for split, summary in dataset.items():
            splits.append(
                {
                    "protocol": name,
                    "split": split,
                    **{key: value for key, value in summary.items() if key != "file"},
                }
            )
        fit = fits[name]
        for split, values in (("validation", fit.validation), ("test", tests[name])):
            for strategy, metrics in values.items():
                results.append(
                    {
                        "protocol": name,
                        "split": split,
                        "strategy": strategy,
                        **metrics,
                        **fit.treatments[strategy],
                    }
                )
    _write_csv(settings.report_dir / "split_summary.csv", splits)
    _write_csv(settings.report_dir / "sampling_comparison.csv", results)
    write_json(settings.report_dir / "audit.json", audit)


def run_sampling(settings: SamplingSettings) -> dict[str, Any]:
    """Publish a new dataset version only after complete sampling and audit success.

    Args:
        settings: A confined new version with approved source and algorithm options.

    Returns:
        Published dataset catalog including artifact fingerprints and split counts.

    Raises:
        FileExistsError: Any requested version destination already exists.
    """
    for path in (settings.data_root, settings.report_dir, settings.catalog):
        if path.exists():
            raise FileExistsError(f"Choose an unused sampling output version: {path}")
    started = time.monotonic()
    manifest = verified_sample_manifest(settings.validation)
    print("Verified stage-two sample and label fingerprints", flush=True)
    settings.data_root.mkdir(parents=True)
    settings.report_dir.mkdir(parents=True)
    datasets, audit = build_partitions(settings, manifest)
    print(
        "Both complete dataset protocols passed label and grouping checks", flush=True
    )
    with threadpool_limits(limits=1):
        fits = {}
        for name, dataset in datasets.items():
            print("Comparing training treatments: " + name, flush=True)
            fits[name] = _fit_protocol(settings, dataset)
        selection = _freeze_selection(fits)
        write_json(settings.report_dir / "validation_selection.json", selection)
        tests = {
            name: _score_test(
                settings,
                dataset,
                fits[name],
                selection["protocols"][name]["thresholds"],
            )
            for name, dataset in datasets.items()
        }
    local_models = settings.data_root / "logistic_controls.joblib"
    joblib.dump(
        {
            "features": settings.features,
            "selection": selection,
            "protocols": {
                name: {"preprocess": fit.preprocess, "models": fit.models}
                for name, fit in fits.items()
            },
        },
        local_models,
        compress=3,
    )
    source_manifest = file_record(settings.validation.report_dir / "samples.json")
    audit.update(
        status="passed",
        source_manifest=source_manifest,
        elapsed_seconds=round(time.monotonic() - started, 6),
        software={
            "system": system(),
            "machine": machine(),
            "python": python_version(),
            **{
                name: version(name)
                for name in ("duckdb", "numpy", "pyarrow", "scikit-learn")
            },
        },
        seed=settings.seed,
        feature_count=len(settings.features),
        test_protocol="Frozen validation thresholds on unchanged natural distributions",
    )
    _write_reports(settings, datasets, fits, tests, audit)
    report_names = (
        "audit.json",
        "split_summary.csv",
        "sampling_comparison.csv",
        "validation_selection.json",
    )
    catalog = {
        "kind": "stage3_purchase_samples",
        "status": "passed",
        "labeled_rows_per_protocol": manifest["sample_rows"],
        "source_manifest": source_manifest,
        "data_root": settings.data_root.relative_to(PROJECT_ROOT).as_posix(),
        "features": list(settings.features),
        "time_anchors": manifest["splits"],
        "seed": settings.seed,
        "target_negative_per_positive": settings.negative_per_positive,
        "smote_neighbors": settings.smote_neighbors,
        "model_control": {
            "estimator": "LogisticRegression",
            "solver": "lbfgs",
            "C": 1,
            "max_iter": _MAX_ITER,
            "tol": 0.0001,
        },
        "protocols": datasets,
        "models": file_record(local_models),
        "reports": [file_record(settings.report_dir / name) for name in report_names],
        "storage": "Git holds aggregate evidence. Data and fitted models stay local.",
    }
    settings.catalog.parent.mkdir(parents=True, exist_ok=True)
    with settings.catalog.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(catalog, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return catalog
