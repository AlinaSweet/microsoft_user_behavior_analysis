"""Fit encoders and materialize bounded, key-aligned transformed feature matrices."""

from dataclasses import asdict
from typing import Any

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd
from scipy import sparse  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.completion_repository import completion_inputs
from user_behavior_analysis.dao.validation_repository import iter_sample_frames
from user_behavior_analysis.dao.validation_repository import verified_sample_manifest
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.models.encoding_models import CompletionSettings
from user_behavior_analysis.models.validation_models import FeatureTransform
from user_behavior_analysis.service.sparse_embedding import completion_matrix
from user_behavior_analysis.service.sparse_embedding import fit_completion_transform
from user_behavior_analysis.service.target_encoding import encode_target
from user_behavior_analysis.service.target_encoding import fit_target_encoding
from user_behavior_analysis.service.validation_preprocessing import transform_record
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import require_contract


def prepare_completion(settings: CompletionSettings) -> dict[str, Any]:
    """Fit all new transformations on complete train and export every snapshot.

    Args:
        settings: Fixed new encoding/output contract.

    Returns:
        Transformation, full row alignment and matrix fingerprint manifest.

    Raises:
        FileExistsError: A destination already exists.
        ValueError: Fit boundaries, source records or generated values disagree.
    """
    if settings.data_root.exists() or settings.report_dir.exists():
        raise FileExistsError("Use unused completion directories")
    source = verified_sample_manifest(settings.validation)
    selection = completion_inputs(settings)["selection"]
    raw = selection["preprocessing"]
    numeric = FeatureTransform(
        **{
            k: raw[k]
            for k in (
                "columns",
                "medians",
                "means",
                "scales",
                "categories",
                "missing_indicators",
            )
        }
    )
    anchor = settings.validation.options["splits"]["train"]
    train = next(s for s in source["snapshots"] if s["anchor"] == anchor)
    columns = ["user_id", "as_of_time", "target"] + list(numeric.categories)
    frame = pd.concat(
        list(iter_sample_frames(train["sample_parts"], columns)), ignore_index=True
    )
    require_contract(
        frame.as_of_time.nunique() == 1
        and str(frame.as_of_time.iloc[0].date()) == anchor,
        "Training cutoff mismatch",
    )
    target = fit_target_encoding(
        frame,
        settings.options["target_column"],
        settings.options["target_folds"],
        settings.options["target_smoothing"],
        train["label_end_exclusive"],
    )
    state, metadata = fit_completion_transform(
        frame,
        numeric,
        target,
        settings.options["embedding_dimensions"],
        settings.options["seed"],
    )
    settings.data_root.mkdir(parents=True)
    settings.report_dir.mkdir(parents=True)
    joblib.dump(state, settings.data_root / "transform.joblib")
    write_json(settings.data_root / "target_encoding.json", asdict(target))
    np.savez_compressed(
        settings.data_root / "sparse_embedding.npz",
        components=state.components,
        mean=state.embedding_mean,
        scale=state.embedding_scale,
    )
    names = transform_record(state.numeric)["encoded_columns"]
    names += [
        f"category_embedding_{i:02d}"
        for i in range(settings.options["embedding_dimensions"])
    ]
    write_json(
        settings.data_root / "matrix_columns.json",
        {"columns": names, "targets_in_matrix": False},
    )
    snapshots = _export_matrices(settings, source, state)
    result = {
        "status": "passed",
        "fit_anchor": anchor,
        "fit_split": "train",
        "target_encoding": {
            "column": target.column,
            "folds": settings.options["target_folds"],
            "smoothing": target.smoothing,
            "training_rows": len(frame),
            "training_users": len(target.user_folds),
            "inference_available_at": target.available_at,
            "prior": target.priors["full"],
            "policy": (
                "User-group OOF, including fold-excluded prior"
                + "s; inference uses only mature train labels."
            ),
        },
        "embedding": metadata,
        "encoded_matrix_columns": len(names),
        "column_names": names,
        "transform_file": file_record(settings.data_root / "transform.joblib"),
        "snapshots": snapshots,
        "input_records": source["inputs"],
    }
    write_json(settings.report_dir / "preprocessing.json", result)
    return result


def _export_matrices(
    settings: CompletionSettings, source: dict[str, Any], state: Any
) -> list[dict[str, Any]]:
    """Write per-part CSR matrices and exact same-order row identities separately.

    Args:
        settings: New matrix and sidecar output paths.
        source: Verified original mature samples.
        state: Frozen TE, sparse projection and numeric preparation.

    Returns:
        Every snapshot's row totals, unknown coverage and per-part fingerprints.
    """
    original = completion_inputs(settings)["selection"]["preprocessing"]["columns"]
    result = []
    for snapshot in source["snapshots"]:
        anchor = snapshot["anchor"]
        parts = snapshot["sample_parts"] or next(
            s["parts"]
            for s in read_json_object(settings.validation.wide_catalog)["snapshots"]
            if s["anchor"] == anchor
        )
        columns = list(
            dict.fromkeys(
                original
                + ["as_of_time", "user_id", "item_id"]
                + (["target"] if snapshot["target_available"] else [])
            )
        )
        files, known, rows = [], 0, 0
        for index, part in enumerate(parts):
            blocks, keys = [], []
            for batch in iter_sample_frames(
                [part], columns, settings.options["batch_rows"]
            ):
                matrix = completion_matrix(
                    batch,
                    state,
                    anchor == settings.validation.options["splits"]["train"],
                )
                require_contract(
                    np.isfinite(matrix.data).all(), "Invalid prepared matrix"
                )
                blocks.append(matrix)
                sidecar = batch[["as_of_time", "user_id", "item_id"]].copy()
                sidecar["target_encoding"] = encode_target(
                    batch,
                    state.target,
                    anchor == settings.validation.options["splits"]["train"],
                )
                available = np.column_stack(
                    [
                        batch[name].isin(values).to_numpy()
                        for name, values in state.vocabularies.items()
                    ]
                ).all(axis=1)
                sidecar["embedding_all_known"] = available
                keys.append(sidecar)
                known += int(available.sum())
            combined = sparse.vstack(blocks, format="csr")
            identities = pd.concat(keys, ignore_index=True)
            require_contract(
                len(identities) == combined.shape[0]
                and not identities.duplicated(
                    ["as_of_time", "user_id", "item_id"]
                ).any(),
                "Matrix alignment differs",
            )
            directory = settings.data_root / "matrices" / anchor
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"part_{index:02d}.npz"
            sparse.save_npz(path, combined)
            identity_path = directory / f"part_{index:02d}_keys.parquet"
            identities.to_parquet(identity_path, index=False, compression="zstd")
            require_contract(
                (sparse.load_npz(path) != combined).nnz == 0, "Matrix roundtrip differs"
            )
            files.append(
                {
                    "matrix": file_record(path),
                    "keys": file_record(identity_path),
                    "source_part": part,
                    "rows": len(identities),
                }
            )
            rows += len(identities)
        require_contract(rows == snapshot["rows"], "Snapshot row count differs")
        print("Prepared matrix " + anchor + ": " + str(rows), flush=True)
        result.append(
            {
                "anchor": anchor,
                "rows": rows,
                "embedding_all_known_rows": known,
                "target_available": snapshot["target_available"],
                "parts": files,
            }
        )
    return result
