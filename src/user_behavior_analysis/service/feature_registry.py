"""Generate feature expressions and matching dictionary records from one registry."""

from typing import Any

from user_behavior_analysis.models.feature_models import FeatureDefinition

ENTITY_KEYS = {
    "user": ["user_id"],
    "item": ["item_id", "category_id"],
    "category": ["category_id"],
    "pair": ["user_id", "item_id", "category_id"],
    "user_category": ["user_id", "category_id"],
}
BEHAVIORS = ((1, "pv"), (2, "fav"), (3, "cart"), (4, "buy"))
CHINESE = {
    "user": "用户",
    "item": "商品",
    "category": "类目",
    "pair": "用户商品对",
    "user_category": "用户类目",
}


def feature_definition(
    table: str,
    name: str,
    expression: str,
    description: str,
    options: dict[str, Any] | None = None,
) -> FeatureDefinition:
    """Create one documented field definition.

    Args:
        table: Owning entity table.
        name: Globally unique field name.
        expression: SQL expression or explicit transformation formula.
        description: Business meaning and interpretation limits.
        options: Optional family, window, dtype and missing-value settings.

    Returns:
        One dictionary record excluding identifiers and labels from feature counts.
    """
    values = options or {}
    return {
        "table": table,
        "name": name,
        "family": values.get("family", "基础统计"),
        "chinese_name": description.split("；")[0],
        "calculation": expression,
        "description": description,
        "window_days": values.get("window_days"),
        "dtype": values.get("dtype", "float64"),
        "missing_policy": values.get(
            "missing_policy", "计数无记录为0；分母为0的比率保留缺失"
        ),
        "available_before_anchor": True,
        "preprocessing": values.get(
            "preprocessing", "保留原始数值；后续按训练期拟合变换与筛选"
        ),
        "artifact": "snapshots/{anchor}/" + table + "_features.parquet",
        "status": "pending",
    }


def window_feature_definitions(
    table: str, windows: list[int]
) -> list[FeatureDefinition]:
    """Define raw counts, key counts, active times and distinct-entity statistics.

    Args:
        table: Registered entity grain.
        windows: Positive historical window lengths.

    Returns:
        SQL-backed definitions for all configured windows.
    """
    output = []
    diversity = {
        "user": [("items", "item_id"), ("categories", "category_id")],
        "item": [("users", "user_id")],
        "category": [("users", "user_id"), ("items", "item_id")],
        "pair": [],
        "user_category": [("items", "item_id")],
    }
    for days in windows:
        condition = "event_time >= $start_" + str(days)
        expressions = [
            (
                "event_count",
                "COALESCE(SUM(raw_count) FILTER(WHERE " + condition + "),0)::BIGINT",
                "有效原始记录数",
            ),
            (
                "key_count",
                "COUNT(*) FILTER(WHERE " + condition + ")::BIGINT",
                "不同四元组数",
            ),
            (
                "active_days",
                "COUNT(DISTINCT event_date) FILTER(WHERE " + condition + ")::BIGINT",
                "有记录的自然日数",
            ),
            (
                "active_hours",
                "COUNT(DISTINCT event_time) FILTER(WHERE " + condition + ")::BIGINT",
                "有记录的小时桶数",
            ),
        ]
        for code, behavior in BEHAVIORS:
            predicate = condition + " AND behavior_type=" + str(code)
            expressions.extend(
                [
                    (
                        behavior + "_count",
                        "COALESCE(SUM(raw_count) FILTER(WHERE "
                        + predicate
                        + "),0)::BIGINT",
                        behavior + "原始记录数",
                    ),
                    (
                        behavior + "_key_count",
                        "COUNT(*) FILTER(WHERE " + predicate + ")::BIGINT",
                        behavior + "不同四元组数",
                    ),
                ]
            )
        for label, identifier in diversity[table]:
            expressions.append(
                (
                    "distinct_" + label,
                    "COUNT(DISTINCT "
                    + identifier
                    + ") FILTER(WHERE "
                    + condition
                    + ")::BIGINT",
                    "不同" + label + "数量",
                )
            )
        for suffix, expression, meaning in expressions:
            output.append(
                feature_definition(
                    table,
                    table + "_" + suffix + "_" + str(days) + "d",
                    expression,
                    CHINESE[table]
                    + "过去"
                    + str(days)
                    + "天"
                    + meaning
                    + "；严格只读截点前；实际覆盖不足由管理字段标记",
                    {"window_days": days, "dtype": "int64"},
                )
            )
    for suffix, expression, meaning in [
        (
            "recency_hours",
            "date_diff('hour',MAX(event_time),$anchor)::DOUBLE",
            "距最近一次观测行为的小时数",
        ),
        (
            "observed_age_days",
            "date_diff('hour',MIN(event_time),$anchor)/24.0",
            "首次观测距截点的天数，不是注册年龄",
        ),
        (
            "buy_recency_hours",
            (
                "date_diff('hour',MAX(event_time) FILTER("
                + "WHERE behavior_type=4),$anchor)::DOUBLE"
            ),
            "距最近一次观测购买的小时数，无历史购买为缺失",
        ),
    ]:
        output.append(
            feature_definition(
                table,
                table + "_" + suffix,
                expression,
                CHINESE[table] + meaning,
                {
                    "family": "生命周期",
                    "missing_policy": "无历史购买的购买间隔保留缺失",
                },
            )
        )
    return output


def derived_feature_definitions(
    table: str, weights: dict[str, int]
) -> list[FeatureDefinition]:
    """Define interpretable ratios and behavior-weighted preference candidates.

    Args:
        table: Registered entity prefix.
        weights: Declared ascending behavior weights.

    Returns:
        Expressions reading only historical statistics.
    """
    prefix = table + "_"
    raw = prefix + "event_count_7d"
    keys = prefix + "key_count_7d"
    score = "+".join(
        str(weights[name]) + "*" + prefix + name + "_key_count_7d"
        for name in ("pv", "fav", "cart", "buy")
    )
    expressions = [
        (
            "weighted_key_score_7d",
            score,
            "行为权重加总的四元组强度；购买>加购>收藏>浏览，权重为业务假设",
        ),
        (
            "extra_same_key_share_7d",
            "(" + raw + "-" + keys + ")::DOUBLE/NULLIF(" + raw + ",0)",
            "额外同键记录占原记录比例，不代表错误日志比例",
        ),
        (
            "purchase_record_share_7d",
            prefix + "buy_count_7d::DOUBLE/NULLIF(" + raw + ",0)",
            "购买记录占行为记录的比例，不是顺序转化率",
        ),
        (
            "active_day_share_7d",
            prefix + "active_days_7d::DOUBLE/NULLIF(history_coverage_7d,0)",
            "观测历史内活跃自然日占比",
        ),
    ]
    if table == "item":
        expressions.append(
            (
                "heat_decay_ratio",
                "("
                + prefix
                + "key_count_3d/3.0)/NULLIF(("
                + prefix
                + "key_count_7d-"
                + prefix
                + "key_count_3d)/4.0,0)",
                "最近3日日均四元组量相对更早4日日均量；非指数衰减参数",
            )
        )
    else:
        expressions.append(
            (
                "recent_activity_ratio",
                prefix + "event_count_1d/NULLIF(" + raw + "/7.0,0)",
                "最近1日原始量相对过去7日日均量",
            )
        )
    return [
        feature_definition(
            table,
            prefix + suffix,
            expression,
            CHINESE[table] + meaning,
            {"family": "行为强度与偏好", "window_days": 7},
        )
        for suffix, expression, meaning in expressions
    ]
