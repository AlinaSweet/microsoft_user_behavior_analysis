"""Construct hour-aware sequence statistics and bounded chronological inputs."""

from typing import Any

import duckdb

from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.feature_registry import feature_definition


def sequence_statistics(
    connection: duckdb.DuckDBPyConnection,
    parameters: dict[str, Any],
    maximum_gap: int,
) -> list[FeatureDefinition]:
    """Compute intervals and multi-label transitions between observed active hours.

    Args:
        connection: Snapshot cache with honest multi-behavior history_hours.
        parameters: Historical cutoff parameters.
        maximum_gap: Largest gap included in transition denominators.

    Returns:
        User-level sequence-feature definitions.

    Notes:
        Multiple behaviors can coexist in an hour; transition rows need not sum
        to one. Last observations are censored rather than interpreted as exits.
    """
    connection.execute(
        "CREATE TABLE sequence_hours AS WITH ordered AS (SELECT *,"
        + (
            " LEAD(event_time) OVER w AS next_time,LE"
            + "AD(behavior_mask) OVER w AS next_mask,"
        )
        + (
            " LAG(event_time) OVER w AS prior_time,LA"
            + "G(behavior_mask) OVER w AS prior_mask"
        )
        + " FROM history_hours WHERE event_time >= $start_7"
        + " WINDOW w AS(PARTITION BY user_id ORDER BY event_time))"
        + " SELECT *,date_diff('hour',event_time,next_time) AS next_gap,"
        + " date_diff('hour',prior_time,event_time) AS prior_gap FROM ordered",
        {"start_7": parameters["start_7"]},
    )
    fields = [
        (
            "mean_gap_hours_7d",
            "AVG(next_gap)::DOUBLE",
            "相邻观测活跃小时的平均间隔，末次记录不参与",
        ),
        ("max_gap_hours_7d", "MAX(next_gap)::DOUBLE", "历史7天最大相邻活跃小时间隔"),
        (
            "multiple_behavior_hour_share_7d",
            "SUM(bit_count(behavior_mask)>1)::DOUBLE/COUNT(*)",
            "同一用户小时出现多行为的比例",
        ),
        (
            "observed_transition_pairs_7d",
            "COUNT(*) FILTER(WHERE next_gap>0 AND next_gap<=" + str(maximum_gap) + ")",
            "间隔不超过阈值的相邻活跃小时对数量",
        ),
    ]
    types = ("pv", "fav", "cart", "buy")
    for origin_index, origin in enumerate(types):
        for destination_index, destination in enumerate(types):
            source_bit = 1 << origin_index
            target_bit = 1 << destination_index
            predicate = (
                "next_gap>0 AND next_gap<="
                + str(maximum_gap)
                + " AND (behavior_mask & "
                + str(source_bit)
                + ")>0"
            )
            fields.append(
                (
                    origin + "_to_" + destination + "_prob_7d",
                    "COUNT(*) FILTER(WHERE "
                    + predicate
                    + " AND (next_mask & "
                    + str(target_bit)
                    + ")>0)::DOUBLE/NULLIF(COUNT(*) FILTER(WHERE "
                    + predicate
                    + "),0)",
                    "当前小时含"
                    + origin
                    + "时，下一观测小时含"
                    + destination
                    + "的条件比例；多标签非互斥",
                )
            )
    definitions = [
        feature_definition(
            "user",
            "user_seq_" + name,
            expression,
            meaning,
            {
                "family": "小时序列",
                "window_days": 7,
                "dtype": (
                    "int64" if name == "observed_transition_pairs_7d" else "float64"
                ),
            },
        )
        for name, expression, meaning in fields
    ]
    connection.execute(
        "CREATE TABLE user_sequence AS SELECT user_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in definitions)
        + " FROM sequence_hours GROUP BY user_id"
    )
    connection.execute(
        "CREATE TABLE sequence_runs AS WITH groups AS(SELECT *,"
        + " SUM(CASE WHEN prior_mask IS DISTINCT FROM behavior_mask OR prior_gap>"
        + str(maximum_gap)
        + " THEN 1 ELSE 0 END)"
        + " OVER(PARTITION BY user_id ORDER BY event_time) AS mask_run,"
        + " SUM(CASE WHEN prior_gap IS DISTINCT FROM 1 THEN 1 ELSE 0 END)"
        + " OVER(PARTITION BY user_id ORDER BY event_time) AS hour_run"
        + " FROM sequence_hours), m AS(SELECT user_id,mask_run,COUNT(*) AS size"
        + " FROM groups GROUP BY user_id,mask_run), h AS(SELECT user_id,hour_run,"
        + " COUNT(*) AS size FROM groups GROUP BY user_id,hour_run)"
        + " SELECT u.user_id,m.max_mask_run,h.max_hour_run FROM user_stats u"
        + " LEFT JOIN(SELECT user_id,MAX(size) AS max_mask_run FROM m"
        + " GROUP BY user_id)m USING(user_id)"
        + " LEFT JOIN(SELECT user_id,MAX(size) AS max_hour_run FROM h"
        + " GROUP BY user_id)h USING(user_id)"
    )
    run_defs = [
        feature_definition(
            "user",
            "user_seq_max_same_mask_run_7d",
            "COALESCE(max_mask_run,0)",
            "相邻活跃小时连续出现相同行为集合的最长长度；间隔超24小时断开",
            {"family": "小时序列", "window_days": 7, "dtype": "int64"},
        ),
        feature_definition(
            "user",
            "user_seq_max_contiguous_hour_run_7d",
            "COALESCE(max_hour_run,0)",
            "连续自然小时都有记录的最长小时桶长度",
            {"family": "小时序列", "window_days": 7, "dtype": "int64"},
        ),
    ]
    connection.execute(
        "CREATE TABLE user_sequence_runs AS SELECT user_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in run_defs)
        + " FROM sequence_runs"
    )
    return definitions + run_defs


def export_sequence_inputs(
    connection: duckdb.DuckDBPyConnection,
    settings: FeatureSettings,
    anchor: str,
    parameters: dict[str, Any],
) -> tuple[dict[str, Any], list[FeatureDefinition]]:
    """Export bounded hour-item sequences while preserving ties and original counts.

    Args:
        connection: Snapshot cache containing cutoff-restricted history.
        settings: Configured sequence length and destination.
        anchor: Snapshot calendar date.
        parameters: Bound historical window starts.

    Returns:
        Persisted sequence metadata and logical input-field definitions.

    Notes:
        Tied items use deterministic ID ordering solely for storage. A truncation
        boundary that cuts a tied hour is explicitly marked.
    """
    length = int(settings.options["sequence_length"])
    connection.execute(
        "CREATE TABLE sequence_units AS WITH units AS(SELECT user_id,item_id,"
        + "category_id,event_time,bit_or(1 << (behavior_type-1)) AS behavior_mask,"
        + ",".join(
            "COALESCE(SUM(raw_count) FILTER(WHERE behavior_type="
            + str(code)
            + "),0)::BIGINT AS "
            + name
            + "_count"
            for code, name in ((1, "pv"), (2, "fav"), (3, "cart"), (4, "buy"))
        )
        + " FROM history WHERE event_time >= $start_30"
        + " GROUP BY user_id,item_id,category_id,event_time), ranked AS(SELECT *,"
        + " COUNT(*) OVER(PARTITION BY user_id) AS original_units,"
        + " COUNT(*) OVER(PARTITION BY user_id,event_time) AS original_hour_units,"
        + " row_number() OVER(PARTITION BY user_id ORDER BY event_time DESC,item_id)"
        + " AS reverse_rank FROM units), retained AS(SELECT * FROM ranked"
        + " WHERE reverse_rank <= $length) SELECT *,"
        + " date_diff('hour',LAG(event_time) OVER(PARTITION BY user_id"
        + " ORDER BY event_time,item_id),event_time) AS gap_hours,"
        + " MIN(event_time) OVER(PARTITION BY user_id) AS oldest_retained_time"
        + " FROM retained",
        {"start_30": parameters["start_30"], "length": length},
    )
    ordering = " ORDER BY event_time,item_id"
    expressions = [
        "list(item_id" + ordering + ") AS seq_item_ids",
        "list(category_id" + ordering + ") AS seq_category_ids",
        "list(behavior_mask" + ordering + ") AS seq_behavior_masks",
        "list(COALESCE(gap_hours,0)" + ordering + ") AS seq_gap_hours",
        "list([pv_count,fav_count,cart_count,buy_count]"
        + ordering
        + ") AS seq_raw_behavior_counts",
        "list(original_hour_units>1" + ordering + ") AS seq_tied_hour_flags",
        "COUNT(*) AS sequence_length",
        "MAX(original_units) AS original_units_30d",
        "MAX(original_units)>$length AS sequence_truncated",
        "COUNT(*) FILTER(WHERE event_time=oldest_retained_time)<"
        + " MAX(original_hour_units) FILTER(WHERE event_time=oldest_retained_time)"
        + " AS boundary_hour_truncated",
        "MAX(event_time) AS source_max_event_time",
    ]
    for bucket in range(16):
        statement = (
            "CREATE TABLE sequence_inputs AS "
            if bucket == 0
            else "INSERT INTO sequence_inputs "
        )
        connection.execute(
            statement
            + "SELECT user_id,"
            + ",".join(expressions)
            + " FROM sequence_units WHERE hash(user_id)%16=$bucket GROUP BY user_id",
            {"length": length, "bucket": bucket},
        )
    directory = settings.output_dir / "snapshots" / anchor
    evidence = export_relation(
        connection,
        "SELECT * FROM sequence_inputs ORDER BY user_id",
        directory / "user_sequences.parquet",
    )
    logical = [
        ("seq_item_ids", "按小时升序的商品ID列表；并列ID排序是技术顺序"),
        ("seq_category_ids", "与商品列表逐位对齐的类目ID"),
        ("seq_behavior_masks", "同一用户商品小时的多行为集合掩码"),
        ("seq_gap_hours", "相邻保留单位的小时间隔；同小时为0"),
        ("seq_raw_behavior_counts", "每单位浏览/收藏/加购/购买原始条数四维向量"),
        ("seq_tied_hour_flags", "同小时多商品的顺序未知标记"),
    ]
    definitions = [
        feature_definition(
            "sequence",
            name,
            "历史30天最近" + str(length) + "个小时商品单位",
            meaning,
            {
                "family": "序列输入",
                "window_days": 30,
                "dtype": "list",
                "missing_policy": "Parquet为真实长度；NPZ用PAD=0、UNK=1并显式mask",
            },
        )
        for name, meaning in logical
    ]
    for row in definitions:
        row["artifact"] = "snapshots/{anchor}/user_sequences.parquet"
    return evidence, definitions
