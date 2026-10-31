"""Construct lifecycle, RF proxies, preference and competition features."""

from typing import Any

import duckdb

from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.service.feature_registry import feature_definition


def create_history_hours(connection: duckdb.DuckDBPyConnection) -> None:
    """Aggregate historical source records into honest multi-behavior hour buckets.

    Args:
        connection: Snapshot cache containing the cutoff-restricted history table.
    """
    connection.execute(
        "CREATE TABLE history_hours AS SELECT user_id,event_time,event_date,"
        + " SUM(raw_count)::BIGINT AS raw_count,COUNT(*) AS key_count,"
        + " bit_or(1 << (behavior_type-1)) AS behavior_mask,"
        + " SUM(raw_count) FILTER(WHERE behavior_type=4) AS buy_count"
        + " FROM history GROUP BY user_id,event_time,event_date"
    )


def lifecycle_features(
    connection: duckdb.DuckDBPyConnection, parameters: dict[str, Any]
) -> list[FeatureDefinition]:
    """Compute observed lifecycle and explicitly non-monetary RF proxy fields.

    Args:
        connection: Snapshot cache with user statistics and history hours.
        parameters: Bound anchor and required historical starts.

    Returns:
        Definitions of the user lifecycle component.

    Notes:
        Recency is observational; proxy states do not prove registration or churn.
    """
    connection.execute(
        "CREATE TABLE user_lifecycle_source AS WITH d AS ("
        + "SELECT DISTINCT user_id,event_date FROM history"
        + " WHERE event_time >= $start_7), g AS (SELECT *,"
        + " event_date-row_number() OVER(PARTITION BY user_id ORDER BY event_date)"
        + " *INTERVAL 1 DAY AS run_group FROM d), runs AS (SELECT user_id,"
        + " COUNT(*) AS run_length,MAX(event_date) AS last_date FROM g"
        + " GROUP BY user_id,run_group), streaks AS (SELECT user_id,"
        + " MAX(run_length) AS max_streak,MAX(CASE WHEN last_date="
        + "CAST($anchor AS DATE)-1 THEN run_length ELSE 0 END) AS current_streak"
        + " FROM runs GROUP BY user_id), h AS (SELECT user_id,"
        + " SUM(raw_count>90) AS flagged_hours,MAX(raw_count) AS max_hour_count,"
        + " SUM(key_count) FILTER(WHERE hour(event_time)<6)::DOUBLE/"
        + " NULLIF(SUM(key_count),0) AS night_share,"
        + " SUM(key_count) FILTER(WHERE isodow(event_time)>5)::DOUBLE/"
        + " NULLIF(SUM(key_count),0) AS weekend_share,"
        + " SUM(sin(2*pi()*hour(event_time)/24)*key_count)/SUM(key_count) AS hour_sin,"
        + " SUM(cos(2*pi()*hour(event_time)/24)*key_count)/SUM(key_count) AS hour_cos"
        + " FROM history_hours WHERE event_time >= $start_7 GROUP BY user_id),"
        + " purchases AS (SELECT user_id,COUNT(DISTINCT event_date) AS purchase_days"
        + " FROM history WHERE behavior_type=4 AND event_time >= $start_30"
        + " GROUP BY user_id) SELECT u.user_id,u.user_recency_hours,"
        + "u.user_buy_recency_hours,u.user_observed_age_days,u.user_key_count_7d,"
        + "u.user_buy_key_count_30d,COALESCE(p.purchase_days,0) AS purchase_days,"
        + "COALESCE(s.max_streak,0) AS max_streak,"
        + "COALESCE(s.current_streak,0) AS current_streak,"
        + "COALESCE(h.flagged_hours,0) AS flagged_hours,"
        + "COALESCE(h.max_hour_count,0) AS max_hour_count,"
        + "h.night_share,h.weekend_share,h.hour_sin,h.hour_cos"
        + " FROM user_stats u LEFT JOIN streaks s USING(user_id)"
        + " LEFT JOIN h USING(user_id) LEFT JOIN purchases p USING(user_id)",
        {name: parameters[name] for name in ("anchor", "start_7", "start_30")},
    )
    fields = [
        (
            "current_active_streak_7d",
            "current_streak",
            "截至截点前一天的连续活跃天数",
            "int64",
        ),
        ("max_active_streak_7d", "max_streak", "历史7天最长连续活跃天数", "int64"),
        (
            "flagged_hour_count_7d",
            "flagged_hours",
            "历史7天超过90条的小时数，只标记",
            "int64",
        ),
        (
            "max_hour_record_count_7d",
            "max_hour_count",
            "历史7天单小时最大原始记录量",
            "int64",
        ),
        (
            "purchase_days_30d",
            "purchase_days",
            "历史30天不同购买日期数；覆盖不足另标记",
            "int64",
        ),
        (
            "night_key_share_7d",
            "COALESCE(night_share,0)",
            "凌晨0至5时四元组占比",
            "float64",
        ),
        (
            "weekend_key_share_7d",
            "COALESCE(weekend_share,0)",
            "周六周日四元组占比，非法定工作日历",
            "float64",
        ),
        ("hour_sin_mean_7d", "hour_sin", "按四元组量加权的小时周期正弦均值", "float64"),
        ("hour_cos_mean_7d", "hour_cos", "按四元组量加权的小时周期余弦均值", "float64"),
        (
            "activity_level_7d",
            "CASE WHEN user_key_count_7d<10 THEN 0 WHEN user_key_count_7d<50"
            + " THEN 1 WHEN user_key_count_7d<200 THEN 2 ELSE 3 END",
            "按7天四元组数10/50/200固定边界划分活跃等级",
            "int64",
        ),
        (
            "rf_recency_score",
            "CASE WHEN user_buy_recency_hours IS NULL THEN 0"
            + " WHEN user_buy_recency_hours<=24 THEN 5"
            + " WHEN user_buy_recency_hours<=72 THEN 4"
            + " WHEN user_buy_recency_hours<=168 THEN 3"
            + " WHEN user_buy_recency_hours<=336 THEN 2 ELSE 1 END",
            "最近购买间隔代理分，无购买为0",
            "int64",
        ),
        (
            "rf_frequency_score",
            "CASE WHEN purchase_days=0 THEN 0 WHEN purchase_days=1 THEN 1"
            + " WHEN purchase_days=2 THEN 2 WHEN purchase_days<5 THEN 3 ELSE 4 END",
            "不同购买日期频率代理分",
            "int64",
        ),
        (
            "purchase_count_proxy_score",
            "CASE WHEN user_buy_key_count_30d=0 THEN 0"
            + " WHEN user_buy_key_count_30d=1 THEN 1"
            + " WHEN user_buy_key_count_30d<5 THEN 2"
            + " WHEN user_buy_key_count_30d<10 THEN 3 ELSE 4 END",
            "购买四元组次数代理分，不是Monetary",
            "int64",
        ),
        (
            "rf_segment",
            "CASE WHEN user_buy_recency_hours<=168 AND purchase_days>=2"
            + " THEN 'high_value_proxy' WHEN user_recency_hours<=72"
            + " THEN 'potential_proxy' WHEN user_recency_hours<=168"
            + " THEN 'at_risk_proxy' ELSE 'dormant_proxy' END",
            "RF行为代理分群：高价值/潜力/风险/沉睡均为观测代理",
            "category",
        ),
        (
            "lifecycle_state",
            "CASE WHEN user_observed_age_days<=3 THEN 'new_observed'"
            + " WHEN user_recency_hours>168 THEN 'dormant_observed'"
            + " WHEN user_recency_hours<=24 THEN 'recently_active'"
            + " ELSE 'less_recently_active' END",
            "首次观测与最近活跃状态，不等同账户生命周期",
            "category",
        ),
    ]
    definitions = [
        feature_definition(
            "user",
            "user_" + name,
            expression,
            meaning,
            {"family": "生命周期与RF代理", "dtype": dtype},
        )
        for name, expression, meaning, dtype in fields
    ]
    connection.execute(
        "CREATE TABLE user_lifecycle AS SELECT user_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in definitions)
        + " FROM user_lifecycle_source"
    )
    return definitions


def preference_features(
    connection: duckdb.DuckDBPyConnection, parameters: dict[str, Any]
) -> list[FeatureDefinition]:
    """Compare within-user preference shares and historical category concentration.

    Args:
        connection: Snapshot cache containing entity statistics.
        parameters: Historical boundary values.

    Returns:
        User, user-category and pair preference component definitions.
    """
    connection.execute(
        "CREATE TABLE category_preferences AS SELECT user_id,category_id,"
        + " COUNT(*) AS key_count,COUNT(*)::DOUBLE/SUM(COUNT(*))"
        + " OVER(PARTITION BY user_id) AS share,"
        + " row_number() OVER(PARTITION BY user_id"
        + " ORDER BY COUNT(*) DESC,category_id) AS preference_rank"
        + " FROM history WHERE event_time >= $start_7 GROUP BY user_id,category_id",
        {"start_7": parameters["start_7"]},
    )
    user_defs = [
        feature_definition(
            "user",
            "user_top_category_key_share_7d",
            "MAX(share)",
            "用户最偏好类目四元组占比",
            {"family": "偏好", "window_days": 7},
        ),
        feature_definition(
            "user",
            "user_category_entropy_7d",
            "CASE WHEN COUNT(*)=1 THEN 0 ELSE"
            + " -SUM(share*ln(share))/ln(COUNT(*)) END",
            "用户类目分布归一化熵；无历史为缺失",
            {"family": "偏好", "window_days": 7},
        ),
        feature_definition(
            "user",
            "user_preferred_category_7d",
            "MAX(category_id) FILTER(WHERE preference_rank=1)",
            "历史7天最偏好类目ID，并列按ID确定性选择",
            {"family": "偏好", "window_days": 7, "dtype": "category"},
        ),
    ]
    connection.execute(
        "CREATE TABLE user_preference AS SELECT user_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in user_defs)
        + " FROM category_preferences GROUP BY user_id"
    )
    uc_defs = [
        feature_definition(
            "user_category",
            "user_category_key_share_7d",
            "c.user_category_key_count_7d::DOUBLE/NULLIF(u.user_key_count_7d,0)",
            "候选类目在该用户历史7天四元组中的份额",
            {"family": "偏好", "window_days": 7},
        ),
        feature_definition(
            "user_category",
            "user_category_weighted_preference_7d",
            (
                "c.user_category_weighted_key_score_7d/NU"
                + "LLIF(u.user_weighted_key_score_7d,0)"
            ),
            "候选类目行为加权强度占用户总加权强度的份额",
            {"family": "偏好", "window_days": 7},
        ),
    ]
    connection.execute(
        "CREATE TABLE user_category_preference AS SELECT c.user_id,c.category_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in uc_defs)
        + " FROM user_category_stats c JOIN user_stats u USING(user_id)"
    )
    pair_defs = [
        feature_definition(
            "pair",
            "pair_user_key_share_7d",
            "p.pair_key_count_7d::DOUBLE/NULLIF(u.user_key_count_7d,0)",
            "候选商品在用户历史7天四元组中的份额",
            {"family": "偏好", "window_days": 7},
        )
    ]
    connection.execute(
        "CREATE TABLE pair_preference AS SELECT p.user_id,p.item_id,p.category_id,"
        + pair_defs[0]["calculation"]
        + " AS "
        + pair_defs[0]["name"]
        + " FROM pair_stats p JOIN user_stats u USING(user_id)"
    )
    return user_defs + uc_defs + pair_defs


def item_competition_features(
    connection: duckdb.DuckDBPyConnection,
) -> list[FeatureDefinition]:
    """Compute same-window purchase coverage and within-category item competition.

    Args:
        connection: Snapshot cache containing pair, item and category statistics.

    Returns:
        Item and category component definitions.
    """
    connection.execute(
        "CREATE TABLE pair_coverages AS SELECT item_id,category_id,"
        + " COUNT(*) FILTER(WHERE pair_pv_count_7d>0) AS view_pairs,"
        + " COUNT(*) FILTER(WHERE pair_buy_count_7d>0) AS buy_pairs,"
        + " COUNT(*) FILTER(WHERE pair_pv_count_7d>0 AND pair_buy_count_7d>0)"
        + " AS converted_pairs FROM pair_stats GROUP BY item_id,category_id"
    )
    item_fields = [
        ("view_user_count_7d", "COALESCE(p.view_pairs,0)", "浏览该商品的不同用户数"),
        ("buy_user_count_7d", "COALESCE(p.buy_pairs,0)", "购买该商品的不同用户数"),
        (
            "same_window_purchase_coverage_7d",
            "p.converted_pairs::DOUBLE/NULLIF(p.view_pairs,0)",
            "同期浏览用户中购买同商品的比例，不保证先后顺序",
        ),
        (
            "category_key_share_7d",
            "i.item_key_count_7d::DOUBLE/NULLIF(c.category_key_count_7d,0)",
            "商品四元组热度占所属类目热度的份额",
        ),
        (
            "category_competition_index_7d",
            "i.item_key_count_7d*c.category_distinct_items_7d::DOUBLE"
            + "/NULLIF(c.category_key_count_7d,0)",
            "商品热度相对所属类目活跃商品平均热度",
        ),
    ]
    output = [
        feature_definition(
            "item",
            "item_" + name,
            expr,
            meaning,
            {"family": "商品生命周期与竞争", "window_days": 7},
        )
        for name, expr, meaning in item_fields
    ]
    connection.execute(
        "CREATE TABLE item_business AS SELECT i.item_id,i.category_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in output)
        + " FROM item_stats i JOIN category_stats c USING(category_id)"
        + " LEFT JOIN pair_coverages p USING(item_id,category_id)"
    )
    category_defs = [
        feature_definition(
            "category",
            "category_view_pair_count_7d",
            "SUM(view_pairs)",
            "类目内不同浏览用户商品对数",
            {"family": "类目覆盖", "window_days": 7, "dtype": "int64"},
        ),
        feature_definition(
            "category",
            "category_same_window_purchase_coverage_7d",
            "SUM(converted_pairs)::DOUBLE/NULLIF(SUM(view_pairs),0)",
            "类目内浏览用户商品对同期购买覆盖，不是顺序转化",
            {"family": "类目覆盖", "window_days": 7},
        ),
    ]
    connection.execute(
        "CREATE TABLE category_business AS SELECT category_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in category_defs)
        + " FROM pair_coverages GROUP BY category_id"
    )
    return output + category_defs
