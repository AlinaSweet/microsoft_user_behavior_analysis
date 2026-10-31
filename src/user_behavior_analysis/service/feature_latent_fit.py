"""Fit frozen sparse SVD factors and bounded item-neighborhood association rules."""

import gc
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix  # type: ignore[import-untyped]
from scipy.sparse import save_npz  # type: ignore[import-untyped]
from sklearn.decomposition import TruncatedSVD  # type: ignore[import-untyped]
from sklearn.preprocessing import normalize  # type: ignore[import-untyped]
from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.models.feature_models import FeatureSettings


def interaction_matrix(
    frame: pd.DataFrame, users: pd.Index, items: pd.Index, weights: dict[str, int]
) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
    """Build weighted historical user-item interactions without dense one-hot arrays.

    Args:
        frame: One row per historically observed candidate pair.
        users: Deterministic user row index.
        items: Frozen item vocabulary.
        weights: Declared pv/fav/cart/buy preference weights.

    Returns:
        Sparse log-strength matrix and known/all pair counts per user.
    """
    row = users.get_indexer(pd.Index(frame["user_id"]))
    column = items.get_indexer(pd.Index(frame["item_id"]))
    known = column >= 0
    strength = np.zeros(len(frame), dtype=np.float32)
    for name in ("pv", "fav", "cart", "buy"):
        strength += weights[name] * frame["pair_" + name + "_key_count_7d"].to_numpy(
            dtype=np.float32
        )
    values = np.log1p(strength[known]).astype(np.float32)
    matrix = csr_matrix(
        (values, (row[known], column[known])),
        shape=(len(users), len(items)),
        dtype=np.float32,
    )
    return (
        matrix,
        np.bincount(row[known], minlength=len(users)),
        np.bincount(row, minlength=len(users)),
    )


def _fit_item_graph(
    matrix: csr_matrix, items: pd.Index, settings: FeatureSettings, directory: Path
) -> dict[str, Any]:
    """Fit TopK item-neighborhood rules within a disclosed training-only universe.

    Args:
        matrix: Training user-item interaction matrix with one nonzero per pair.
        items: Frozen item ID order.
        settings: Minimum support, maximum item universe and neighbor limits.
        directory: Local latent artifact directory.

    Returns:
        Universe, support and actual rule-count evidence.

    Notes:
        Rules use unordered seven-day user baskets and do not represent causal
        effects or click-order transitions.
    """
    support = np.bincount(matrix.indices, minlength=len(items))
    eligible = np.flatnonzero(support >= settings.options["cooccurrence_min_users"])
    selected = eligible[
        np.lexsort((items.to_numpy()[eligible], -support[eligible]))[
            : settings.options["cooccurrence_max_items"]
        ]
    ]
    selected_ids = items.to_numpy()[selected]
    baskets = matrix[:, selected].copy()
    baskets.data = np.ones_like(baskets.data, dtype=np.float32)
    overlap = (baskets.T @ baskets).tocsr()
    overlap.setdiag(0)
    overlap.eliminate_zeros()
    rows = []
    maximum = int(settings.options["cooccurrence_neighbors"])
    for index, source in enumerate(selected_ids):
        start, end = overlap.indptr[index : index + 2]
        targets = overlap.indices[start:end]
        joint = overlap.data[start:end]
        keep = joint >= 2
        targets = targets[keep]
        joint = joint[keep]
        cosine = joint / np.sqrt(support[selected[index]] * support[selected[targets]])
        ranked = np.lexsort((selected_ids[targets], -cosine))[:maximum]
        for position in ranked:
            source_support = int(support[selected[index]])
            target_support = int(support[selected[targets[position]]])
            confidence = float(joint[position]) / source_support
            rows.append(
                {
                    "source_item_id": str(source),
                    "target_item_id": str(selected_ids[targets[position]]),
                    "cooccurring_users": int(joint[position]),
                    "source_users": source_support,
                    "target_users": target_support,
                    "cosine": float(cosine[position]),
                    "jaccard": float(joint[position])
                    / (source_support + target_support - float(joint[position])),
                    "confidence": confidence,
                    "lift": confidence / (target_support / matrix.shape[0]),
                    "support": float(joint[position]) / matrix.shape[0],
                }
            )
    pd.DataFrame({"item_id": selected_ids}).to_parquet(
        directory / "graph_items.parquet", index=False
    )
    pd.DataFrame(
        rows,
        columns=[
            "source_item_id",
            "target_item_id",
            "cooccurring_users",
            "source_users",
            "target_users",
            "cosine",
            "jaccard",
            "confidence",
            "lift",
            "support",
        ],
    ).to_parquet(directory / "item_neighbors.parquet", index=False)
    return {
        "training_users": matrix.shape[0],
        "minimum_item_users": settings.options["cooccurrence_min_users"],
        "eligible_items": len(eligible),
        "selected_items": len(selected),
        "maximum_neighbors": maximum,
        "minimum_joint_users": 2,
        "rules": len(rows),
        "semantics": "unordered training-window user baskets; no observed click order",
    }


def fit_frozen_latent(settings: FeatureSettings) -> dict[str, Any]:
    """Fit IDF, vocabularies, SVD and association rules before the earliest cutoff.

    Args:
        settings: Feature configuration with a single declared fit anchor.

    Returns:
        Frozen-model dimensions, provenance, coverage and association metadata.

    Raises:
        ValueError: An existing model uses different fit parameters or input data.
    """
    directory = settings.output_dir / "latent"
    directory.mkdir(parents=True, exist_ok=True)
    metadata_path = directory / "metadata.json"
    configuration = {
        "fit_anchor": settings.options["fit_anchor"],
        "components": settings.options["svd_components"],
        "weights": settings.options["behavior_weights"],
        "base_catalog_sha256": sha256_file(
            settings.base_dir.parents[1] / "catalog/base_raw_v2.json"
        ),
    }
    if metadata_path.exists():
        metadata: dict[str, Any] = json.loads(metadata_path.read_text())
        if metadata["configuration"] != configuration:
            raise ValueError("Frozen latent fit changed; select a new output version")
        return metadata
    anchor = settings.options["fit_anchor"]
    database = settings.output_dir / "snapshots" / anchor / "features.duckdb"
    with feature_connection(settings, database) as connection:
        pairs = connection.execute(
            "SELECT user_id,item_id,pair_pv_key_count_7d,pair_fav_key_count_7d,"
            + "pair_cart_key_count_7d,pair_buy_key_count_7d FROM pair_stats"
        ).df()
        users = pd.Index(
            connection.execute("SELECT user_id FROM user_stats ORDER BY user_id").df()[
                "user_id"
            ]
        )
        item_categories = connection.execute(
            "SELECT item_id,category_id FROM item_stats ORDER BY item_id"
        ).df()
    items = pd.Index(item_categories["item_id"])
    matrix, _, _ = interaction_matrix(
        pairs, users, items, settings.options["behavior_weights"]
    )
    del pairs
    gc.collect()
    item_support = np.bincount(matrix.indices, minlength=len(items))
    idf = (np.log1p(len(users) / (1 + item_support))).astype(np.float32)
    weighted = matrix.multiply(idf).tocsr()
    weighted = normalize(weighted, axis=1, copy=False)
    model = TruncatedSVD(
        n_components=settings.options["svd_components"],
        algorithm="randomized",
        n_iter=3,
        n_oversamples=8,
        random_state=42,
    )
    with threadpool_limits(limits=settings.options["threads"]):
        transformed = model.fit_transform(weighted).astype(np.float32)
    components = model.components_.astype(np.float32)
    np.save(directory / "svd_components.npy", components)
    np.save(directory / "idf.npy", idf)
    norms = np.sqrt((components * components).sum(axis=0)).astype(np.float32)
    np.save(directory / "item_factor_norms.npy", norms)
    save_npz(directory / "training_interactions.npz", matrix, compressed=True)
    item_categories["item_token"] = np.arange(len(items), dtype=np.int32) + 2
    item_categories.to_parquet(directory / "item_vocabulary.parquet", index=False)
    categories = sorted(item_categories["category_id"].unique())
    pd.DataFrame(
        {
            "category_id": categories,
            "category_token": np.arange(len(categories), dtype=np.int32) + 2,
        }
    ).to_parquet(directory / "category_vocabulary.parquet", index=False)
    factors = pd.DataFrame(
        components.T,
        columns=[
            "item_svd_" + str(i).zfill(2)
            for i in range(settings.options["svd_components"])
        ],
    )
    factors.insert(0, "item_id", items.to_numpy())
    factors["item_svd_norm"] = norms
    factors["item_svd_known"] = np.ones(len(items), dtype=np.int8)
    factors.to_parquet(directory / "item_factors.parquet", index=False)
    graph = _fit_item_graph(matrix, items, settings, directory)
    metadata = {
        "configuration": configuration,
        "fit_history_start": str(pd.Timestamp(anchor) - pd.Timedelta(days=7)),
        "fit_history_end_exclusive": anchor + " 00:00:00",
        "users": len(users),
        "items": len(items),
        "interaction_pairs": matrix.nnz,
        "matrix_shape": list(matrix.shape),
        "matrix_dtype": str(matrix.dtype),
        "sparsity": 1 - matrix.nnz / (len(users) * len(items)),
        "components": int(components.shape[0]),
        "explained_variance_ratio": model.explained_variance_ratio_.tolist(),
        "explained_variance_sum": float(model.explained_variance_ratio_.sum()),
        "training_user_embedding_shape": list(transformed.shape),
        "normalization": "log1p weighted key strength; frozen item IDF; per-user L2",
        "graph": graph,
        "padding_token": 0,
        "unknown_token": 1,
        "uses_future_labels": False,
    }
    write_json(metadata_path, metadata)
    write_json(settings.report_dir / "latent_fit.json", metadata)
    return metadata
