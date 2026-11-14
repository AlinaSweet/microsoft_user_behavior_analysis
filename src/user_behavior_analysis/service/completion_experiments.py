"""Compare frozen OHE references with TE and sparse-embedding group ablations."""

import time
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
import psutil
from scipy import sparse  # type: ignore[import-untyped]
from sklearn.linear_model import SGDClassifier  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.completion_repository import completion_inputs
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.encoding_models import CompletionSettings
from user_behavior_analysis.service.validation_groups import COHORT_COLUMNS
from user_behavior_analysis.service.validation_groups import cohort_masks
from user_behavior_analysis.service.validation_metrics import clustered_auc_deltas
from user_behavior_analysis.service.validation_metrics import prediction_metrics
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import require_contract


def _indices(settings: CompletionSettings, columns: list[str]) -> dict[str, np.ndarray]:
    """Map the unchanged selected groups to the new prepared matrix columns.

    Args:
        settings: Fixed experiment groups.
        columns: Exact transformed matrix column order.

    Returns:
        Encoded column indices for each predeclared experiment.
    """
    groups = completion_inputs(settings)["selection"]["selected_groups"]
    groups["embedding"] = [
        name for name in columns if name.startswith("category_embedding_")
    ]
    result = {}
    for name, requested in settings.options["experiments"].items():
        fields = [field for group in requested for field in groups[group]]
        result[name] = np.array(
            [
                i
                for i, column in enumerate(columns)
                if any(
                    column == field or column.startswith(field + "__")
                    for field in fields
                )
            ]
        )
        require_contract(len(result[name]) > 0, "Empty comparison group")
    return result


def _read_part(record: dict[str, Any]) -> tuple[Any, pd.DataFrame]:
    """Verify one materialized matrix, identities and its accepted source part.

    Args:
        record: Fingerprinted prepared part and original sample identity.

    Returns:
        CSR inputs and same-order original target/cohort rows.
    """
    matrix = sparse.load_npz(verify_registered_file(record["matrix"]))
    identities = pd.read_parquet(verify_registered_file(record["keys"]))
    frame = pd.read_parquet(
        verify_registered_file(record["source_part"]),
        columns=["as_of_time"] + COHORT_COLUMNS,
    )
    require_contract(
        np.array_equal(
            frame[["as_of_time", "user_id", "item_id"]].to_numpy(),
            identities[["as_of_time", "user_id", "item_id"]].to_numpy(),
        ),
        "Matrix/source keys differ",
    )
    require_contract(
        len(frame) == matrix.shape[0] == record["rows"], "Matrix/source rows differ"
    )
    frame["embedding_all_known"] = identities.embedding_all_known.to_numpy()
    return matrix, frame


def _train(
    snapshot: dict[str, Any],
    indices: dict[str, np.ndarray],
    settings: CompletionSettings,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit fixed logistic models on identical complete training records.

    Args:
        snapshot: Prepared full training matrices.
        indices: Group-specific matrix projections.
        settings: Predeclared SGD configuration.

    Returns:
        Six fitted models and complete row-visit/resource evidence.
    """
    models = {
        name: SGDClassifier(
            loss="log_loss",
            penalty="l2",
            alpha=0.0001,
            learning_rate="invscaling",
            eta0=0.01,
            power_t=0.25,
            average=True,
            random_state=settings.options["seed"],
        )
        for name in indices
    }
    generator = np.random.default_rng(settings.options["seed"])
    visits, peak, started = [], 0, time.monotonic()
    for epoch in range(settings.options["epochs"]):
        count = 0
        for index in generator.permutation(len(snapshot["parts"])):
            matrix, frame = _read_part(snapshot["parts"][index])
            for start in range(0, len(frame), settings.options["batch_rows"]):
                stop = min(start + settings.options["batch_rows"], len(frame))
                order = start + generator.permutation(stop - start)
                for name, model in models.items():
                    model.partial_fit(
                        matrix[order][:, indices[name]],
                        frame.target.to_numpy()[order],
                        classes=np.array([0, 1]),
                    )
                count += len(order)
            peak = max(peak, psutil.Process().memory_info().rss)
        require_contract(count == snapshot["rows"], "Incomplete training epoch")
        visits.append(count)
        print("TE comparison epoch " + str(epoch + 1) + ": " + str(count), flush=True)
    return models, {
        "rows_per_epoch_per_model": visits,
        "seconds": time.monotonic() - started,
        "observed_peak_rss_bytes": peak,
        "columns": {name: len(v) for name, v in indices.items()},
    }


def _predict(
    snapshot: dict[str, Any],
    fitted: tuple[dict[str, Any], dict[str, np.ndarray]],
    settings: CompletionSettings,
) -> pd.DataFrame:
    """Predict complete held-out rows with fixed unknown-feature fallbacks.

    Args:
        snapshot: One mature prepared held-out cutoff.
        fitted: Frozen logistic models and their matrix columns.
        settings: Output paths and accepted OHE reference location.

    Returns:
        Full same-order candidate scores and original observed outcomes.
    """
    models, indices = fitted
    old = read_json_object(settings.validation.report_dir / "experiments.json")
    split = next(
        name
        for name, anchor in settings.validation.options["splits"].items()
        if anchor == snapshot["anchor"]
    )
    reference = pd.read_parquet(
        verify_registered_file(old["evaluations"][split]["file"]),
        columns=["user_id", "item_id", "target", "basic", "business"],
    )
    outputs, offset = [], 0
    for part in snapshot["parts"]:
        matrix, frame = _read_part(part)
        base = reference.iloc[offset : offset + len(frame)]
        require_contract(
            np.array_equal(
                frame[["user_id", "item_id", "target"]].to_numpy(),
                base[["user_id", "item_id", "target"]].to_numpy(),
            ),
            "OHE comparison population differs",
        )
        output = frame.copy()
        output["basic"], output["business"] = (
            base.basic.to_numpy(),
            base.business.to_numpy(),
        )
        for name, model in models.items():
            values = []
            for start in range(0, len(frame), settings.options["batch_rows"]):
                values.append(
                    model.predict_proba(
                        matrix[start : start + settings.options["batch_rows"]][
                            :, indices[name]
                        ]
                    )[:, 1]
                )
            output[name] = np.concatenate(values)
        no_svd, no_graph = (
            output.pair_svd_available == 0,
            output.pair_cooc_graph_known == 0,
        )
        output.loc[no_svd, "te_svd"] = output.loc[no_svd, "te_business"]
        output.loc[no_graph, "te_cooccurrence"] = output.loc[no_graph, "te_business"]
        output.loc[no_svd & no_graph, "te_combined"] = output.loc[
            no_svd & no_graph, "te_sequence"
        ]
        missing = ~output.embedding_all_known
        output.loc[missing, "te_preembedding"] = output.loc[missing, "te_business"]
        outputs.append(output)
        offset += len(frame)
    require_contract(
        offset == snapshot["rows"] == len(reference), "Evaluation coverage differs"
    )
    result = pd.concat(outputs, ignore_index=True)
    destination = settings.data_root / "predictions" / (snapshot["anchor"] + ".parquet")
    destination.parent.mkdir(exist_ok=True)
    result.to_parquet(destination, index=False, compression="zstd")
    return result


def _metrics(frame: pd.DataFrame, models: list[str], seed: int) -> dict[str, Any]:
    """Evaluate all pairs and separately inspect feature coverage and user cohorts.

    Args:
        frame: Complete fixed same-row scores and targets.
        models: Reference and newly fitted experiment names.
        seed: Paired user-cluster bootstrap seed.

    Returns:
        Exact metrics and fixed-reference AUC uncertainty.
    """
    masks = cohort_masks(frame)
    masks["preembedding_available"] = frame.embedding_all_known.to_numpy()
    masks["preembedding_unavailable"] = ~frame.embedding_all_known.to_numpy()
    output = {
        cohort: {
            name: prediction_metrics(
                frame.target.to_numpy()[mask], frame[name].to_numpy()[mask]
            )
            for name in models
        }
        for cohort, mask in masks.items()
    }
    output["clustered_auc_deltas"] = clustered_auc_deltas(
        frame.target.to_numpy(),
        {name: frame[name].to_numpy() for name in models},
        pd.factorize(frame.user_id)[0],
        100,
        seed,
    )
    return output


def run_completion_experiments(settings: CompletionSettings) -> dict[str, Any]:
    """Freeze validation selection before evaluating all predeclared test comparisons.

    Args:
        settings: Prepared feature and comparison configuration.

    Returns:
        Full TE/OHE/embedding and feature-group comparison report.

    Raises:
        FileExistsError: The new comparison has already completed.
    """
    destination = settings.report_dir / "encoding_experiments.json"
    if destination.exists():
        raise FileExistsError(destination)
    preparation = read_json_object(settings.report_dir / "preprocessing.json")
    snapshots = {s["anchor"]: s for s in preparation["snapshots"]}
    indices = _indices(settings, preparation["column_names"])
    train = settings.validation.options["splits"]["train"]
    models, training = _train(snapshots[train], indices, settings)
    path = settings.data_root / "models.joblib"
    joblib.dump({"models": models, "indices": indices}, path)
    result: dict[str, Any] = {
        "status": "passed",
        "training": training,
        "model_file": file_record(path),
        "evaluations": {},
    }
    names = ["basic", "business"] + list(models)
    for split in ("validation", "test"):
        anchor = settings.validation.options["splits"][split]
        frame = _predict(snapshots[anchor], (models, indices), settings)
        measured = _metrics(frame, names, settings.options["seed"])
        if split == "validation":
            chosen = max(
                (value["average_precision"], name)
                for name, value in measured["all"].items()
            )[1]
            result["validation_choice"] = chosen
            write_json(
                settings.report_dir / "encoding_validation_choice.json",
                {
                    "model": chosen,
                    "criterion": "validation AP",
                    "test_read_for_choice": False,
                },
            )
        result["evaluations"][split] = {
            "anchor": anchor,
            "metrics": measured,
            "prediction_file": file_record(
                settings.data_root / "predictions" / (anchor + ".parquet")
            ),
        }
        print("Completed encoding comparison: " + split, flush=True)
    write_json(destination, result)
    return result
