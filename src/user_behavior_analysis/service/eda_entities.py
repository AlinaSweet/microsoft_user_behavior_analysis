"""Compare support-aware entity rankings and descriptive category preferences."""

import numpy as np
import pandas as pd

from user_behavior_analysis.dao.eda_repository import read_cache_frame
from user_behavior_analysis.dao.eda_repository import read_source_frame
from user_behavior_analysis.models.eda_models import EDASettings
from user_behavior_analysis.service.eda_statistics import wilson_interval


def _rank_entities(frame: pd.DataFrame, minimum: int) -> pd.DataFrame:
    """Rank sufficiently observed entities by the lower coverage-rate bound.

    Args:
        frame: Item or category profiles with pair counts.
        minimum: Required observed browsing user-item pairs.

    Returns:
        Up to twenty entities with explicit support and coverage intervals.
    """
    result = frame.loc[frame["view_pairs"] >= minimum].copy()
    result["coverage_rate"] = result["converted_pairs"] / result["view_pairs"]
    result["lower"], result["upper"] = wilson_interval(
        result["converted_pairs"], result["view_pairs"]
    )
    return (
        result.sort_values(["lower", "view_pairs"], ascending=False)
        .head(20)
        .reset_index(drop=True)
    )


def entity_tables(
    settings: EDASettings, tables: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    """Compute support-aware rankings, long-tail shares and item quadrants.

    Args:
        settings: EDA ranking thresholds.
        tables: Full-period category profiles.

    Returns:
        Ranked entities, category cumulative shares and eligible item quadrants.
    """
    categories = tables["categories"]
    top_items = read_cache_frame(
        settings, "SELECT * FROM item_profiles ORDER BY events DESC, item_id LIMIT 20"
    )
    candidate_items = read_cache_frame(
        settings,
        "SELECT * FROM item_profiles WHERE view_pairs >= :minimum",
        {"minimum": settings["min_item_view_pairs"]},
    )
    item_rate = _rank_entities(candidate_items, settings["min_item_view_pairs"])
    item_ids = sorted(set(top_items["item_id"]) | set(item_rate["item_id"]))
    parameters = {f"item_{index}": value for index, value in enumerate(item_ids)}
    placeholders = ", ".join(":" + name for name in parameters)
    item_categories = read_source_frame(
        settings,
        "SELECT item_id, category_id FROM items WHERE item_id IN ("
        + placeholders
        + ")",
        parameters,
    )
    top_items = top_items.merge(item_categories, on="item_id", validate="one_to_one")
    item_rate = item_rate.merge(item_categories, on="item_id", validate="one_to_one")
    tail = categories.sort_values(["pv", "category_id"], ascending=[False, True]).copy()
    tail["rank"] = range(1, len(tail) + 1)
    tail["category_share"] = tail["rank"] / len(tail)
    tail["cumulative_pv_share"] = tail["pv"].cumsum() / tail["pv"].sum()
    tail["cumulative_buy_share"] = tail["buy"].cumsum() / tail["buy"].sum()
    quadrants = read_cache_frame(
        settings,
        "SELECT * FROM item_profiles WHERE view_pairs >= :minimum",
        {"minimum": settings["quadrant_min_view_pairs"]},
    )
    prior = float(categories["converted_pairs"].sum() / categories["view_pairs"].sum())
    quadrants["smoothed_coverage"] = (quadrants["converted_pairs"] + 20 * prior) / (
        quadrants["view_pairs"] + 20
    )
    threshold = float(quadrants["pv"].median())
    quadrants["quadrant"] = np.select(
        [
            quadrants["pv"].ge(threshold) & quadrants["smoothed_coverage"].ge(prior),
            quadrants["pv"].ge(threshold) & quadrants["smoothed_coverage"].lt(prior),
            quadrants["pv"].lt(threshold) & quadrants["smoothed_coverage"].ge(prior),
        ],
        ["高浏览高覆盖", "高浏览低覆盖", "低浏览高覆盖"],
        default="低浏览低覆盖",
    )
    return {
        "top_items_volume": top_items,
        "top_items_coverage": item_rate,
        "top_categories_volume": categories.sort_values(
            ["events", "category_id"], ascending=[False, True]
        ).head(20),
        "top_categories_coverage": _rank_entities(
            categories, settings["min_category_view_pairs"]
        ),
        "category_tail": tail,
        "item_quadrants": quadrants,
        "quadrant_thresholds": pd.DataFrame(
            [
                {
                    "minimum_view_pairs": settings["quadrant_min_view_pairs"],
                    "pv_record_median": threshold,
                    "coverage_prior": prior,
                    "prior_weight": 20,
                    "eligible_items": len(quadrants),
                }
            ]
        ),
    }


def preference_tables(
    settings: EDASettings, users: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """Compare category preferences across full-period activity tertiles.

    Args:
        settings: Validated cache location.
        users: Full-period profiles used only for descriptive strata.

    Returns:
        Top-five preferences per stratum and a shared-category comparison.
    """
    low, high = users["events"].quantile([1 / 3, 2 / 3]).tolist()
    frame = read_cache_frame(
        settings,
        "SELECT CASE WHEN u.events <= :low THEN '低活跃'"
        + " WHEN u.events <= :high THEN '中活跃' ELSE '高活跃' END AS activity,"
        + " c.category_id, SUM(c.events) AS events,"
        + " SUM(c.event_keys) AS event_keys, COUNT(*) AS users"
        + " FROM user_categories c JOIN user_profiles u USING (user_id)"
        + " GROUP BY activity, c.category_id",
        {"low": low, "high": high},
    )
    for column in ("events", "event_keys"):
        frame[column + "_share"] = frame[column] / frame.groupby("activity")[
            column
        ].transform("sum")
    top = (
        frame.sort_values(
            ["activity", "event_keys", "category_id"], ascending=[True, False, True]
        )
        .groupby("activity", sort=False)
        .head(5)
    )
    shared_ids = frame.groupby("category_id")["event_keys"].sum().nlargest(10).index
    return {
        "preference_top5": top,
        "preference_shared": frame.loc[frame["category_id"].isin(shared_ids)],
        "activity_thresholds": pd.DataFrame(
            [
                {
                    "low_upper": low,
                    "middle_upper": high,
                    "basis": "full-period raw records; descriptive only",
                }
            ]
        ),
    }
