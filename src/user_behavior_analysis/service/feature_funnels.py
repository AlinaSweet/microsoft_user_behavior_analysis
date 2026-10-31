"""Build strict-hour historical path features without treating counts as transitions."""

from typing import Any

import duckdb

from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.service.feature_registry import ENTITY_KEYS
from user_behavior_analysis.service.feature_registry import feature_definition


def funnel_features(
    connection: duckdb.DuckDBPyConnection, parameters: dict[str, Any]
) -> list[FeatureDefinition]:
    """Compute observed strict-hour path states within the historical seven-day window.

    Args:
        connection: Snapshot cache with the complete cutoff-restricted history.
        parameters: Bound historical starts.

    Returns:
        Pair path states and properly conditional aggregate path ratios.

    Notes:
        These describe paths already observed inside the feature window.
        Recent views have less observation time; these are not mature seven-day
        purchase-conversion estimates. Same-hour order remains unknown.
    """
    connection.execute(
        "CREATE TABLE funnel_views AS SELECT user_id,item_id,category_id,"
        + " MIN(event_time) FILTER(WHERE behavior_type=1) AS first_pv"
        + " FROM history WHERE event_time >= $start_7"
        + " GROUP BY user_id,item_id,category_id",
        {"start_7": parameters["start_7"]},
    )
    prior = "funnel_views"
    for name, code, previous in (
        ("cart", 3, "pv"),
        ("fav", 2, "cart"),
        ("buy", 4, "fav"),
    ):
        target = "funnel_" + name
        connection.execute(
            "CREATE TABLE "
            + target
            + " AS SELECT f.*,"
            + " (SELECT MIN(h.event_time) FROM history h WHERE h.user_id=f.user_id"
            + " AND h.item_id=f.item_id AND h.behavior_type="
            + str(code)
            + " AND h.event_time>f.first_"
            + previous
            + ") AS first_"
            + name
            + " FROM "
            + prior
            + " f"
        )
        prior = target
    connection.execute("CREATE VIEW funnel_pairs AS SELECT * FROM funnel_buy")
    output = []
    for table, keys in ENTITY_KEYS.items():
        if table == "pair":
            continue
        fields = []
        for name in ("pv", "cart", "fav", "buy"):
            fields.append(
                (
                    "funnel_" + name + "_pairs_7d",
                    "COUNT(*) FILTER(WHERE first_" + name + " IS NOT NULL)",
                    "历史窗口内已观测到严格路径至" + name + "的用户商品对数",
                    "int64",
                )
            )
        for origin, target in (("pv", "cart"), ("cart", "fav"), ("fav", "buy")):
            fields.append(
                (
                    "funnel_" + origin + "_to_" + target + "_rate_7d",
                    "COUNT(*) FILTER(WHERE first_"
                    + target
                    + " IS NOT NULL)::DOUBLE"
                    + "/NULLIF(COUNT(*) FILTER(WHERE first_"
                    + origin
                    + " IS NOT NULL),0)",
                    "同历史队列已观测严格路径" + origin + "至" + target + "条件覆盖率",
                    "float64",
                )
            )
        definitions = [
            feature_definition(
                table,
                table + "_" + name,
                expr,
                meaning,
                {"family": "严格小时漏斗", "window_days": 7, "dtype": dtype},
            )
            for name, expr, meaning, dtype in fields
        ]
        connection.execute(
            "CREATE TABLE "
            + table
            + "_funnel AS SELECT "
            + ",".join(keys)
            + ","
            + ",".join(row["calculation"] + " AS " + row["name"] for row in definitions)
            + " FROM funnel_pairs GROUP BY "
            + ",".join(keys)
        )
        output.extend(definitions)
    pair_defs = []
    for name in ("pv", "cart", "fav", "buy"):
        pair_defs.append(
            feature_definition(
                "pair",
                "pair_funnel_has_" + name + "_7d",
                "(first_" + name + " IS NOT NULL)::INTEGER",
                "候选对在历史7天是否已观测到严格路径至" + name,
                {"family": "严格小时漏斗", "window_days": 7, "dtype": "int64"},
            )
        )
    for origin, target in (("pv", "cart"), ("cart", "fav"), ("fav", "buy")):
        pair_defs.append(
            feature_definition(
                "pair",
                "pair_funnel_" + origin + "_to_" + target + "_gap_hours_7d",
                "date_diff('hour',first_" + origin + ",first_" + target + ")::DOUBLE",
                "已确认严格跨小时路径的间隔；同小时未知或未观测为缺失",
                {"family": "严格小时漏斗", "window_days": 7},
            )
        )
    connection.execute(
        "CREATE TABLE pair_funnel AS SELECT user_id,item_id,category_id,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in pair_defs)
        + " FROM funnel_pairs"
    )
    return output + pair_defs
