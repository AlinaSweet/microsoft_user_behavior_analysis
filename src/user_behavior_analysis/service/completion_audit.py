"""Independently replay every prepared row and saved logistic prediction."""

from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
from scipy import sparse  # type: ignore[import-untyped]
from scipy import special  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.completion_repository import completion_inputs
from user_behavior_analysis.dao.validation_repository import iter_sample_frames
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.encoding_models import CompletionSettings
from user_behavior_analysis.service.sparse_embedding import completion_matrix
from user_behavior_analysis.service.wide_contracts import require_contract


def _audit_matrix(snapshot: dict[str, Any], state: Any) -> dict[str, Any]:
    """Replay every matrix element from its exact source and frozen transformer.

    Args:
        snapshot: All fingerprinted parts for one historical anchor.
        state: Frozen training-only transformations.

    Returns:
        Complete row counts and maximum absolute matrix reconstruction error.
    """
    rows, maximum = 0, 0.0
    for part in snapshot["parts"]:
        matrix = sparse.load_npz(verify_registered_file(part["matrix"]))
        identities = pd.read_parquet(verify_registered_file(part["keys"]))
        offset = 0
        columns = list(
            dict.fromkeys(
                [
                    (
                        name
                        if name != state.target.column + "__te"
                        else state.target.column
                    )
                    for name in state.numeric.columns
                ]
                + list(state.vocabularies)
                + ["as_of_time", "user_id", "item_id"]
            )
        )
        for frame in iter_sample_frames([part["source_part"]], columns, 8192):
            stop = offset + len(frame)
            require_contract(
                np.array_equal(
                    frame[["as_of_time", "user_id", "item_id"]].to_numpy(),
                    identities.iloc[offset:stop][
                        ["as_of_time", "user_id", "item_id"]
                    ].to_numpy(),
                ),
                "Matrix identity order changed",
            )
            replay = completion_matrix(frame, state, snapshot["anchor"] == "2025-11-25")
            difference = replay - matrix[offset:stop]
            error = float(abs(difference).max()) if difference.nnz else 0.0
            maximum = max(maximum, error)
            offset = stop
        require_contract(
            offset == len(identities) == matrix.shape[0], "Matrix coverage differs"
        )
        rows += offset
    require_contract(rows == snapshot["rows"] and maximum == 0, "Matrix replay differs")
    return {
        "anchor": snapshot["anchor"],
        "rows": rows,
        "maximum_absolute_error": maximum,
    }


def _audit_predictions(
    snapshot: dict[str, Any], result: dict[str, Any], fitted: dict[str, Any]
) -> dict[str, Any]:
    """Reconstruct full held-out probabilities directly from saved coefficients.

    Args:
        snapshot: Complete prepared held-out matrices.
        result: Same-row prediction file and evaluation population.
        fitted: Saved logistic parameters and group projections.

    Returns:
        Replayed model counts, candidate rows and numerical errors.
    """
    predictions = pd.read_parquet(verify_registered_file(result["prediction_file"]))
    errors = {name: 0.0 for name in fitted["models"]}
    offset = 0
    for part in snapshot["parts"]:
        matrix = sparse.load_npz(verify_registered_file(part["matrix"]))
        frame = predictions.iloc[offset : offset + matrix.shape[0]]
        values = {}
        for name, model in fitted["models"].items():
            values[name] = special.expit(  # pylint: disable=no-member
                np.asarray(matrix[:, fitted["indices"][name]] @ model.coef_.T).ravel()
                + model.intercept_[0]
            )
        no_svd = frame.pair_svd_available.to_numpy() == 0
        no_graph = frame.pair_cooc_graph_known.to_numpy() == 0
        values["te_svd"][no_svd] = values["te_business"][no_svd]
        values["te_cooccurrence"][no_graph] = values["te_business"][no_graph]
        both = no_svd & no_graph
        values["te_combined"][both] = values["te_sequence"][both]
        missing = ~frame.embedding_all_known.to_numpy()
        values["te_preembedding"][missing] = values["te_business"][missing]
        for name, value in values.items():
            errors[name] = max(
                errors[name], float(np.max(np.abs(value - frame[name].to_numpy())))
            )
        offset += len(frame)
    require_contract(
        offset == len(predictions) == snapshot["rows"], "Prediction coverage differs"
    )
    require_contract(max(errors.values()) < 1e-12, "Saved logistic replay differs")
    return {"anchor": snapshot["anchor"], "rows": offset, "models": errors}


def _audit_target_maps(settings: CompletionSettings, state: Any) -> dict[str, Any]:
    """Compare every frozen target mapping with an independent full-train groupby.

    Args:
        settings: Accepted sample locations and output contract.
        state: Saved training-only target encoder.

    Returns:
        Independently checked full and fold-excluded category counts.
    """
    train = next(
        s
        for s in completion_inputs(settings)["samples"]["snapshots"]
        if s["anchor"] == "2025-11-25"
    )
    frame = pd.concat(
        list(
            iter_sample_frames(
                train["sample_parts"], ["user_id", "target", state.column]
            )
        ),
        ignore_index=True,
    )
    frame["fold"] = frame.user_id.map(state.user_folds)
    checked = 0
    for key, mapping in state.maps.items():
        allowed = frame if key == "full" else frame.loc[frame.fold != int(key)]
        prior = float(allowed.target.mean())
        require_contract(abs(prior - state.priors[key]) < 1e-15, "Target prior differs")
        totals = allowed.groupby(state.column, observed=True).target.agg(
            ["sum", "count"]
        )
        expected = (totals["sum"] + state.smoothing * prior) / (
            totals["count"] + state.smoothing
        )
        require_contract(
            set(mapping) == set(expected.index), "Target categories differ"
        )
        require_contract(
            bool(
                np.allclose(
                    expected.to_numpy(),
                    [mapping[v] for v in expected.index],
                    rtol=0,
                    atol=1e-15,
                )
            ),
            "Target mapping differs",
        )
        checked += len(mapping)
    return {"maps": len(state.maps), "category_entries": checked, "differences": 0}


def audit_completion(settings: CompletionSettings) -> dict[str, Any]:
    """Audit every prepared snapshot, independent target map and saved prediction.

    Args:
        settings: Current completed output contract.

    Returns:
        Full replay and training-only target-map verification evidence.
    """
    prepared = read_json_object(settings.report_dir / "preprocessing.json")
    experiment = read_json_object(settings.report_dir / "encoding_experiments.json")
    state = joblib.load(verify_registered_file(prepared["transform_file"]))
    fitted = joblib.load(verify_registered_file(experiment["model_file"]))
    matrices = []
    predictions = []
    for snapshot in prepared["snapshots"]:
        matrices.append(_audit_matrix(snapshot, state))
        print("Replayed full matrix " + snapshot["anchor"], flush=True)
        for result in experiment["evaluations"].values():
            if result["anchor"] == snapshot["anchor"]:
                predictions.append(_audit_predictions(snapshot, result, fitted))
    result = {
        "status": "passed",
        "matrices": matrices,
        "predictions": predictions,
        "target_maps": _audit_target_maps(settings, state.target),
    }
    write_json(settings.report_dir / "audit.json", result)
    return result
