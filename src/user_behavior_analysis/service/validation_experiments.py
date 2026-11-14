"""Train fixed streaming logistic regressions and evaluate predeclared ablations."""

import time
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import psutil
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from sklearn.linear_model import SGDClassifier  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.validation_repository import iter_sample_frames
from user_behavior_analysis.dao.validation_repository import verified_sample_manifest
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.models.validation_models import FeatureTransform
from user_behavior_analysis.models.validation_models import ValidationSettings
from user_behavior_analysis.service.validation_groups import COHORT_COLUMNS
from user_behavior_analysis.service.validation_groups import cohort_masks
from user_behavior_analysis.service.validation_metrics import clustered_auc_deltas
from user_behavior_analysis.service.validation_metrics import prediction_metrics
from user_behavior_analysis.service.validation_preprocessing import transform_frame
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import require_contract


def _experiment_indices(
    selection: dict[str, Any], options: dict[str, Any]
) -> dict[str, np.ndarray]:
    """Map scalar experiment groups to their frozen encoded matrix columns.

    Args:
        selection: Passed training-only field and preprocessing selection.
        options: Predeclared ablation group combinations.

    Returns:
        Ordered matrix indices for each experiment.
    """
    encoded = selection["preprocessing"]["encoded_columns"]
    result = {}
    for name, groups in options["experiments"].items():
        columns = [
            column for group in groups for column in selection["selected_groups"][group]
        ]
        result[name] = np.array(
            [
                index
                for index, feature in enumerate(encoded)
                if any(
                    feature == column or feature.startswith(column + "__")
                    for column in columns
                )
            ]
        )
        require_contract(len(result[name]) > 0, "Empty experiment: " + name)
    return result


def _fit_models(
    parts: list[dict[str, Any]],
    state: FeatureTransform,
    indices: dict[str, np.ndarray],
    options: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit every linear logistic model on identical complete training rows.

    Args:
        parts: All training parts in the checked sample manifest.
        state: Train-fitted preprocessing state.
        indices: Per-experiment encoded columns.
        options: Fixed SGD optimization, epoch and seed parameters.

    Returns:
        Fitted models and measured training work/resources.
    """
    models = {
        name: SGDClassifier(
            loss="log_loss",
            penalty="l2",
            alpha=options["alpha"],
            learning_rate="invscaling",
            eta0=0.01,
            power_t=0.25,
            average=True,
            random_state=options["seed"],
        )
        for name in indices
    }
    generator = np.random.default_rng(options["seed"])
    started = time.monotonic()
    peak = 0
    visited = []
    columns = list(dict.fromkeys(state.columns + ["target"]))
    for epoch in range(options["epochs"]):
        total = 0
        ordered = [parts[i] for i in generator.permutation(len(parts))]
        for frame in iter_sample_frames(ordered, columns, options["batch_rows"]):
            frame = frame.iloc[generator.permutation(len(frame))]
            matrix = transform_frame(frame, state)
            for name, model in models.items():
                model.partial_fit(
                    matrix[:, indices[name]],
                    frame.target.to_numpy(),
                    classes=np.array([0, 1]),
                )
            total += len(frame)
            peak = max(peak, psutil.Process().memory_info().rss)
        visited.append(total)
        print(
            "Logistic epoch " + str(epoch + 1) + ": " + str(total) + " rows/model",
            flush=True,
        )
    return models, {
        "seconds": time.monotonic() - started,
        "peak_observed_rss_bytes": peak,
        "rows_per_epoch_per_model": visited,
        "optimizer": (
            "SGD averaged linear logistic regression; fixed epo" + "chs; no resampling"
        ),
        "encoded_columns": {name: len(value) for name, value in indices.items()},
    }


def _apply_fallback(predictions: dict[str, np.ndarray], frame: pd.DataFrame) -> None:
    """Use a fixed basic/business fallback where advanced features are unavailable.

    Args:
        predictions: Mutable same-batch probabilities for every experiment.
        frame: Historical coverage flags; no targets are inspected.

    Notes:
        SVD and graph unavailability differ from an observed numeric zero.
    """
    missing_svd = frame.pair_svd_available.to_numpy() == 0
    missing_graph = frame.pair_cooc_graph_known.to_numpy() == 0
    predictions["svd"][missing_svd] = predictions["business"][missing_svd]
    predictions["cooccurrence"][missing_graph] = predictions["business"][missing_graph]
    predictions["combined"][missing_svd & missing_graph] = predictions["sequence"][
        missing_svd & missing_graph
    ]


def _predict_snapshot(
    snapshot: dict[str, Any],
    state: FeatureTransform,
    fitted: tuple[dict[str, Any], dict[str, np.ndarray]],
    settings: ValidationSettings,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Stream exact same-row predictions and retain a reproducible local score table.

    Args:
        snapshot: One complete mature sample cutoff.
        state: Frozen preprocessing contract.
        fitted: Models and their ordered matrix indices.
        settings: Output locations and evaluation parameters.

    Returns:
        Compact full-population score frame and output/resource evidence.
    """
    models, indices = fitted
    columns = list(dict.fromkeys(state.columns + COHORT_COLUMNS))
    records = []
    started = time.monotonic()
    path = settings.sample_root / "predictions" / (snapshot["anchor"] + ".parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    require_contract(not path.exists(), "Prediction file exists")
    writer = None
    try:
        for frame in iter_sample_frames(
            snapshot["sample_parts"], columns, settings.options["batch_rows"]
        ):
            matrix = transform_frame(frame, state)
            predictions = {
                name: model.predict_proba(matrix[:, indices[name]])[:, 1]
                for name, model in models.items()
            }
            _apply_fallback(predictions, frame)
            compact = frame[COHORT_COLUMNS].copy()
            for name, values in predictions.items():
                compact[name] = values
            table = pa.Table.from_pandas(compact, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(path, table.schema, compression="zstd")
            writer.write_table(table)
            records.append(compact)
    finally:
        if writer is not None:
            writer.close()
    result = pd.concat(records, ignore_index=True)
    require_contract(len(result) == snapshot["rows"], "Prediction rows differ")
    return result, {"file": file_record(path), "seconds": time.monotonic() - started}


def _evaluate(frame: pd.DataFrame, options: dict[str, Any]) -> dict[str, Any]:
    """Report full and overlapping cohort metrics plus paired cluster intervals.

    Args:
        frame: Complete same-row observed targets and frozen predictions.
        options: Fixed metric threshold and bootstrap configuration.

    Returns:
        Model-by-cohort metrics and uncertainty relative to business baseline.
    """
    output = {}
    target = frame.target.to_numpy()
    for cohort, mask in cohort_masks(frame).items():
        output[cohort] = {
            name: prediction_metrics(
                target[mask],
                frame[name].to_numpy()[mask],
                options["decision_threshold"],
            )
            for name in options["experiments"]
        }
    output["clustered_auc_deltas"] = clustered_auc_deltas(
        target,
        {name: frame[name].to_numpy() for name in options["experiments"]},
        pd.factorize(frame.user_id)[0],
        options["bootstrap_repeats"],
        options["seed"],
    )
    return output


def run_experiments(settings: ValidationSettings) -> dict[str, Any]:
    """Fit on train, freeze the validation choice, then evaluate the test once.

    Args:
        settings: Checked immutable sample and experiment configuration.

    Returns:
        Honest retrospective ablation results and all prediction artifacts.

    Raises:
        FileExistsError: Experiment results already exist.
        ValueError: Inputs, fit boundaries or row counts disagree.
    """
    destination = settings.report_dir / "experiments.json"
    if destination.exists():
        raise FileExistsError(destination)
    manifest = verified_sample_manifest(settings)
    selection = read_json_object(settings.report_dir / "selection.json")
    require_contract(
        selection["status"] == "passed"
        and selection["fit_anchor"] == settings.options["splits"]["train"],
        "Selection fit boundary",
    )
    raw = selection["preprocessing"]
    state = FeatureTransform(
        **{
            key: raw[key]
            for key in (
                "columns",
                "medians",
                "means",
                "scales",
                "categories",
                "missing_indicators",
            )
        }
    )
    indices = _experiment_indices(selection, settings.options)
    snapshots = {s["anchor"]: s for s in manifest["snapshots"]}
    models, training = _fit_models(
        snapshots[selection["fit_anchor"]]["sample_parts"],
        state,
        indices,
        settings.options,
    )
    model_path = settings.sample_root / "models.joblib"
    joblib.dump(
        {"models": models, "indices": indices, "preprocessing": state}, model_path
    )
    result: dict[str, Any] = {
        "status": "passed",
        "training": training,
        "model_file": file_record(model_path),
        "evaluations": {},
    }
    for split in ("validation", "test"):
        print("Evaluating complete " + split, flush=True)
        anchor = settings.options["splits"][split]
        frame, evidence = _predict_snapshot(
            snapshots[anchor], state, (models, indices), settings
        )
        metrics = _evaluate(frame, settings.options)
        result["evaluations"][split] = dict(evidence, anchor=anchor, metrics=metrics)
        if split == "validation":
            best = max(
                (value["average_precision"], name)
                for name, value in metrics["all"].items()
            )[1]
            result["validation_choice"] = best
            write_json(
                settings.report_dir / "frozen_validation_choice.json",
                {
                    "chosen_experiment": best,
                    "criterion": "validation average precision",
                    "test_read_for_choice": False,
                    "all_experiments_predeclared": True,
                },
            )
        del frame
    result["limitations"] = [
        (
            "Existing EDA inspected these dates; retrospective "
            + "temporal holdout, not a pristine blind test."
        ),
        (
            "One train/validation/test cutoff and 31 source day"
            + "s; no stability across many temporal folds."
        ),
        (
            "Only previously interacted candidates; ranking met"
            + "rics do not include unrecalled future purchases."
        ),
        (
            "Uniform training sample estimates MI; full rows us"
            + "ed for training moments, model fitting and evaluat"
            + "ion."
        ),
        (
            "Fixed five-epoch SGD LR preexperiment; no claim of"
            + " optimized or calibrated production model."
        ),
    ]
    write_json(destination, result)
    return result
