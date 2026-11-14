"""Project training-only sparse categorical inputs into reusable dense vectors."""

from dataclasses import replace
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse  # type: ignore[import-untyped]
from sklearn.decomposition import TruncatedSVD  # type: ignore[import-untyped]

from user_behavior_analysis.models.encoding_models import CompletionTransform
from user_behavior_analysis.models.encoding_models import TargetEncodingState
from user_behavior_analysis.models.validation_models import FeatureTransform
from user_behavior_analysis.service.target_encoding import encode_target
from user_behavior_analysis.service.validation_preprocessing import transform_frame
from user_behavior_analysis.service.wide_contracts import require_contract


def sparse_categories(frame: pd.DataFrame, vocabularies: dict[str, list[str]]) -> Any:
    """Create bounded sparse one-hot blocks using frozen unknown buckets.

    Args:
        frame: Categorical source fields.
        vocabularies: Ordered training-only category lists.

    Returns:
        CSR matrix with one active bucket per categorical field.
    """
    blocks = []
    for name, vocabulary in vocabularies.items():
        mapping = {value: index + 1 for index, value in enumerate(vocabulary)}
        tokens = frame[name].map(mapping).fillna(0).to_numpy(dtype=np.int32)
        blocks.append(
            sparse.csr_matrix(
                (
                    np.ones(len(frame), dtype=np.float32),
                    (np.arange(len(frame)), tokens),
                ),
                shape=(len(frame), len(vocabulary) + 1),
            )
        )
    return sparse.hstack(blocks, format="csr", dtype=np.float32)


def fit_completion_transform(
    frame: pd.DataFrame,
    numeric: FeatureTransform,
    target: TargetEncodingState,
    dimensions: int,
    seed: int,
) -> tuple[CompletionTransform, dict[str, Any]]:
    """Fit a numeric TE scale and unsupervised categorical projection on train.

    Args:
        frame: Full training categorical rows and user groups.
        numeric: Previously frozen training-only preparation.
        target: Cross-fitted target encoder.
        dimensions: Fixed sparse projection size.
        seed: Declared decomposition seed.

    Returns:
        Prepared transform and measured sparse-input/projection metadata.
    """
    values = encode_target(frame, target, True)
    name = target.column + "__te"
    categories = {
        key: value for key, value in numeric.categories.items() if key != target.column
    }
    prepared = replace(
        numeric,
        columns=[name if c == target.column else c for c in numeric.columns],
        categories=categories,
        medians=dict(numeric.medians),
        means=dict(numeric.means),
        scales=dict(numeric.scales),
    )
    prepared.medians[name] = float(np.median(values))
    prepared.means[name] = float(np.mean(values, dtype=np.float64))
    prepared.scales[name] = max(float(np.std(values, dtype=np.float64)), 1e-8)
    matrix = sparse_categories(frame, numeric.categories)
    require_contract(1 <= dimensions < matrix.shape[1], "Embedding dimension bounds")
    model = TruncatedSVD(n_components=dimensions, n_iter=7, random_state=seed)
    projected = model.fit_transform(matrix)
    state = CompletionTransform(
        prepared,
        target,
        numeric.categories,
        model.components_.astype(np.float32),
        projected.mean(axis=0),
        np.maximum(projected.std(axis=0), 1e-8),
    )
    return state, {
        "rows": len(frame),
        "sparse_input_columns": matrix.shape[1],
        "sparse_nonzeros": matrix.nnz,
        "dimensions": dimensions,
        "explained_variance_ratio_sum": float(model.explained_variance_ratio_.sum()),
        "fit_uses_targets": False,
        "fit_split": "train",
    }


def completion_matrix(
    frame: pd.DataFrame, state: CompletionTransform, training: bool
) -> Any:
    """Apply frozen TE, numeric preparation and categorical projection.

    Args:
        frame: One candidate batch with historical inputs and group identity.
        state: Training-only fitted model parameters.
        training: Whether to use cross-fitted training maps.

    Returns:
        CSR matrix with standardized selected fields plus eight embedding axes.
    """
    prepared = frame.copy()
    prepared[state.target.column + "__te"] = encode_target(
        frame, state.target, training
    )
    base = transform_frame(prepared, state.numeric)
    projection = sparse_categories(frame, state.vocabularies) @ state.components.T
    projection = (projection - state.embedding_mean) / state.embedding_scale
    return sparse.hstack(
        [base, sparse.csr_matrix(projection)], format="csr", dtype=np.float32
    )
