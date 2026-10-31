"""Project later histories into frozen latent factors and assemble pair signals."""

from typing import Any

import duckdb
import numpy as np
import pandas as pd
from sklearn.preprocessing import normalize  # type: ignore[import-untyped]

from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.feature_latent_fit import interaction_matrix
from user_behavior_analysis.service.feature_registry import feature_definition


def _embedding_definitions(settings: FeatureSettings) -> list[FeatureDefinition]:
    """Document latent coordinates, known-vocabulary coverage and pair affinity.

    Args:
        settings: Configured SVD dimensionality.

    Returns:
        Explicit scalar dimensions and latent-coverage fields.
    """
    definitions = []
    dimensions = settings.options["svd_components"]
    for entity in ("user", "item"):
        for index in range(dimensions):
            definitions.append(
                feature_definition(
                    entity,
                    entity + "_svd_" + str(index).zfill(2),
                    "frozen training-history IDF/L2/SVD coordinate " + str(index),
                    entity + "隐式语义第" + str(index) + "维；维度无独立业务语义",
                    {
                        "family": "SVD隐式特征",
                        "dtype": "float32",
                        "missing_policy": "未知商品坐标置0，结合known标记",
                    },
                )
            )
    for entity, name, meaning, dtype in [
        ("user", "user_svd_norm", "用户隐式向量L2范数", "float32"),
        (
            "user",
            "user_svd_known_pair_share_7d",
            "历史7天候选对在冻结商品词表中的覆盖",
            "float64",
        ),
        ("user", "user_svd_has_known_history", "是否至少有一个词表内历史商品", "int64"),
        ("item", "item_svd_norm", "冻结商品隐式向量L2范数", "float32"),
        ("item", "item_svd_known", "该商品是否在训练历史词表内", "int64"),
        ("pair", "pair_svd_dot", "用户投影与候选商品向量点积", "float64"),
        ("pair", "pair_svd_cosine", "用户与候选商品隐式向量余弦", "float64"),
        ("pair", "pair_svd_available", "双方具有可用隐式表示的标记", "int64"),
    ]:
        definitions.append(
            feature_definition(
                entity,
                name,
                "frozen latent projection",
                meaning,
                {
                    "family": "SVD隐式特征",
                    "dtype": dtype,
                    "missing_policy": "未知或无已知历史时置0，保留可用性标记",
                },
            )
        )
    return definitions


def transform_latent(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings
) -> tuple[list[FeatureDefinition], dict[str, Any]]:
    """Transform historical windows without refitting vocabulary, IDF or SVD.

    Args:
        connection: One strictly historical snapshot cache.
        settings: Frozen artifacts and SVD settings.

    Returns:
        Produced field definitions and per-snapshot latent coverage.

    Notes:
        Item factors remain fixed across cutoffs, preserving coordinate meaning.
    """
    directory = settings.output_dir / "latent"
    vocabulary = pd.read_parquet(directory / "item_vocabulary.parquet")
    items = pd.Index(vocabulary["item_id"])
    users = pd.Index(
        connection.execute("SELECT user_id FROM user_stats ORDER BY user_id").df()[
            "user_id"
        ]
    )
    pairs = connection.execute(
        "SELECT user_id,item_id,pair_pv_key_count_7d,pair_fav_key_count_7d,"
        + "pair_cart_key_count_7d,pair_buy_key_count_7d FROM pair_stats"
    ).df()
    matrix, known, total = interaction_matrix(
        pairs, users, items, settings.options["behavior_weights"]
    )
    del pairs
    idf = np.load(directory / "idf.npy", mmap_mode="r")
    components = np.load(directory / "svd_components.npy", mmap_mode="r")
    matrix = normalize(matrix.multiply(idf).tocsr(), axis=1, copy=False)
    values = np.asarray(matrix @ components.T, dtype=np.float32)
    frame = pd.DataFrame(
        values,
        columns=[
            "user_svd_" + str(index).zfill(2)
            for index in range(settings.options["svd_components"])
        ],
    )
    frame.insert(0, "user_id", users.to_numpy())
    frame["user_svd_norm"] = np.linalg.norm(values, axis=1)
    frame["user_svd_known_pair_share_7d"] = np.divide(
        known, total, out=np.zeros_like(known, dtype=float), where=total > 0
    )
    frame["user_svd_has_known_history"] = (known > 0).astype(np.int8)
    connection.register("svd_user_frame", frame)
    connection.execute("CREATE TABLE user_svd AS SELECT * FROM svd_user_frame")
    connection.unregister("svd_user_frame")
    connection.read_parquet(str(directory / "item_factors.parquet")).create_view(
        "item_svd"
    )
    dot = "+".join(
        "u.user_svd_"
        + str(index).zfill(2)
        + "*COALESCE(i.item_svd_"
        + str(index).zfill(2)
        + ",0)"
        for index in range(settings.options["svd_components"])
    )
    connection.execute(
        "CREATE TABLE pair_latent AS SELECT p.user_id,p.item_id,p.category_id,"
        + " ("
        + dot
        + ")::DOUBLE AS pair_svd_dot,"
        + " COALESCE(LEAST(1.0,GREATEST(-1.0,("
        + dot
        + ")"
        + " /NULLIF(u.user_svd_norm*i.item_svd_norm,0))),0) AS pair_svd_cosine,"
        + " (COALESCE(i.item_svd_known,0)=1 AND u.user_svd_has_known_history=1)"
        + " ::INTEGER AS pair_svd_available FROM pair_stats p"
        + " JOIN user_svd u USING(user_id) LEFT JOIN item_svd i USING(item_id)"
    )
    availability = require_result_row(
        connection.execute(
            "SELECT COUNT(*),SUM(pair_svd_available) FROM pair_latent"
        ).fetchone()
    )
    return _embedding_definitions(settings), {
        "users": len(users),
        "users_with_known_history": int((known > 0).sum()),
        "mean_known_pair_share_7d": float(frame["user_svd_known_pair_share_7d"].mean()),
        "candidate_pairs": int(availability[0]),
        "available_candidate_pairs": int(availability[1]),
        "vocabulary_frozen": True,
    }


def cooccurrence_features(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings
) -> list[FeatureDefinition]:
    """Score candidate items against user history using frozen TopK item rules.

    Args:
        connection: Snapshot cache with seven-day pair statistics.
        settings: Frozen association artifact directory.

    Returns:
        Pair-level matched-neighborhood and association feature definitions.

    Notes:
        The candidate itself cannot contribute because graph self-edges are absent.
        Uncovered candidates are marked rather than claimed to have zero similarity.
    """
    directory = settings.output_dir / "latent"
    connection.read_parquet(str(directory / "item_neighbors.parquet")).create_view(
        "item_graph"
    )
    connection.read_parquet(str(directory / "graph_items.parquet")).create_view(
        "graph_items"
    )
    connection.execute(
        "CREATE TABLE matched_neighbors AS SELECT p.user_id,p.item_id,p.category_id,"
        + "COUNT(*) AS neighbors,AVG(g.cosine) AS mean_cosine,"
        + "AVG(g.confidence) AS mean_confidence,MAX(g.lift) AS max_lift"
        + " FROM pair_stats p JOIN item_graph g ON p.item_id=g.target_item_id"
        + " JOIN pair_stats h ON h.user_id=p.user_id AND h.item_id=g.source_item_id"
        + " GROUP BY p.user_id,p.item_id,p.category_id"
    )
    fields = [
        (
            "neighbor_count",
            "COALESCE(m.neighbors,0)",
            "候选商品关联到的历史邻居商品数",
            "int64",
        ),
        (
            "mean_cosine",
            "COALESCE(m.mean_cosine,0)",
            "匹配历史邻居的平均共同用户余弦",
            "float64",
        ),
        (
            "rule_mean_confidence",
            "COALESCE(m.mean_confidence,0)",
            "历史邻居指向候选的平均篮子规则置信度",
            "float64",
        ),
        (
            "rule_max_lift",
            "COALESCE(m.max_lift,0)",
            "匹配篮子规则最大lift；不是因果提升",
            "float64",
        ),
        (
            "graph_known",
            "(g.item_id IS NOT NULL)::INTEGER",
            "候选是否在受支持的冻结共现商品集合内",
            "int64",
        ),
    ]
    definitions = [
        feature_definition(
            "pair",
            "pair_cooc_" + name,
            expression,
            meaning,
            {
                "family": "共现与关联规则",
                "dtype": dtype,
                "window_days": 7,
                "missing_policy": "无匹配置0；图覆盖标记为0时不能解释为已观测相似度为0",
            },
        )
        for name, expression, meaning, dtype in fields
    ]
    connection.execute(
        "CREATE TABLE pair_cooccurrence AS SELECT p.user_id,p.item_id,p.category_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in definitions)
        + " FROM pair_stats p LEFT JOIN matched_neighbors m"
        + " USING(user_id,item_id,category_id)"
        + " LEFT JOIN graph_items g USING(item_id)"
    )
    return definitions


def encode_sequence_tensors(
    settings: FeatureSettings, anchor: str, user_ids: pd.Series
) -> dict[str, Any]:
    """Encode saved sequence inputs using frozen dictionaries and explicit masks.

    Args:
        settings: Feature destinations and sequence length.
        anchor: Snapshot date.
        user_ids: Complete historical user population in deterministic order.

    Returns:
        Tensor shapes and unknown-token coverage.
    """
    directory = settings.output_dir
    categories = pd.read_parquet(directory / "latent/category_vocabulary.parquet")
    item_index = pd.Index(
        pd.read_parquet(directory / "latent/item_vocabulary.parquet")["item_id"]
    )
    category_index = pd.Index(categories["category_id"])
    sequences = pd.read_parquet(
        directory / "snapshots" / anchor / "user_sequences.parquet"
    ).set_index("user_id")
    rows = len(user_ids)
    length = settings.options["sequence_length"]
    item_tokens = np.zeros((rows, length), dtype=np.int32)
    category_tokens = np.zeros((rows, length), dtype=np.int32)
    behavior_masks = np.zeros((rows, length), dtype=np.uint8)
    counts = np.zeros((rows, length, 4), dtype=np.uint32)
    gaps = np.zeros((rows, length), dtype=np.int16)
    valid = np.zeros((rows, length), dtype=bool)
    ties = np.zeros((rows, length), dtype=bool)
    gap_defined = np.zeros((rows, length), dtype=bool)
    for index, user_id in enumerate(user_ids):
        if user_id not in sequences.index:
            continue
        row = sequences.loc[user_id]
        size = len(row["seq_item_ids"])
        item_codes = item_index.get_indexer(row["seq_item_ids"])
        category_codes = category_index.get_indexer(row["seq_category_ids"])
        item_tokens[index, :size] = np.where(item_codes < 0, 1, item_codes + 2)
        category_tokens[index, :size] = np.where(
            category_codes < 0, 1, category_codes + 2
        )
        behavior_masks[index, :size] = row["seq_behavior_masks"]
        counts[index, :size, :] = np.asarray(
            list(row["seq_raw_behavior_counts"]), dtype=np.uint32
        )
        gaps[index, :size] = row["seq_gap_hours"]
        valid[index, :size] = True
        ties[index, :size] = row["seq_tied_hour_flags"]
        gap_defined[index, 1:size] = True
    path = directory / "snapshots" / anchor / "sequence_tensors.npz"
    np.savez_compressed(
        path,
        user_ids=np.asarray(user_ids, dtype=str),
        item_tokens=item_tokens,
        category_tokens=category_tokens,
        behavior_masks=behavior_masks,
        raw_behavior_counts=counts,
        gap_hours=gaps,
        valid_mask=valid,
        tied_hour_mask=ties,
        gap_defined_mask=gap_defined,
    )
    return {
        "path": str(path),
        "user_shape": [rows, length],
        "raw_behavior_count_shape": [rows, length, 4],
        "valid_positions": int(valid.sum()),
        "unknown_item_positions": int(((item_tokens == 1) & valid).sum()),
        "padding_token": 0,
        "unknown_token": 1,
        "padding_side": "right",
        "raw_behavior_order": ["pv", "fav", "cart", "buy"],
    }
