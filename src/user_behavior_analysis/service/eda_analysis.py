"""Compute dashboard-one exploratory tables with explicit counting and time units."""

import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.dao.eda_repository import read_cache_frame
from user_behavior_analysis.dao.eda_repository import read_source_frame
from user_behavior_analysis.models.eda_models import EDASettings
from user_behavior_analysis.service.eda_entities import entity_tables
from user_behavior_analysis.service.eda_entities import preference_tables
from user_behavior_analysis.service.eda_statistics import summarize_bins

BEHAVIORS = ("pv", "cart", "fav", "buy")


def _base_tables(settings: EDASettings) -> dict[str, pd.DataFrame]:
    """Read the small full-period tables and derive calendar summaries.

    Args:
        settings: Validated EDA configuration.

    Returns:
        User, hourly, daily, category and repetition-sensitivity tables.
    """
    users = read_cache_frame(settings, "SELECT * FROM user_profiles")
    hours = read_cache_frame(settings, "SELECT * FROM hourly ORDER BY event_time")
    categories = read_cache_frame(settings, "SELECT * FROM category_profiles")
    dates = pd.to_datetime(hours["event_time"])
    hours["event_date"] = dates.dt.strftime("%Y-%m-%d")
    hours["weekday"] = dates.dt.dayofweek
    hours["hour"] = dates.dt.hour
    daily = hours.groupby("event_date")[list(BEHAVIORS) + ["events"]].sum()
    day_users = read_cache_frame(
        settings,
        "SELECT event_date, COUNT(*) AS active_users,"
        + " SUM(buy > 0) AS buy_users FROM user_days GROUP BY event_date",
    ).set_index("event_date")
    daily = daily.join(day_users).reset_index()
    daily["purchase_user_share"] = daily["buy_users"] / daily["active_users"]
    daily["weekday"] = pd.to_datetime(daily["event_date"]).dt.dayofweek
    behavior = pd.DataFrame(
        [
            {
                "behavior": name,
                "raw_records": int(users[name].sum()),
                "four_tuple_keys": int(users[name + "_keys"].sum()),
                "users": int((users[name] > 0).sum()),
            }
            for name in BEHAVIORS
        ]
    )
    return {
        "users": users,
        "hours": hours,
        "daily": daily,
        "categories": categories,
        "behavior_sensitivity": behavior,
    }


def _future_tables(settings: EDASettings) -> dict[str, pd.DataFrame]:
    """Build separate seven-day history and complete future-window EDA cohorts.

    Args:
        settings: Configuration containing anchor dates and positive window lengths.

    Returns:
        Anchor-level label ratios, binned relationships and latest local cohort.

    Raises:
        ValueError: A configured window extends outside observed source dates.
    """
    bounds = read_source_frame(
        settings,
        "SELECT MIN(event_time) AS first, MAX(event_time) AS last"
        + " FROM event_times",
    ).iloc[0]
    sql = (PROJECT_ROOT / "sql/eda/forward_user_cohort.sql").read_text()
    summaries = []
    relationships = []
    latest = pd.DataFrame()
    for anchor_text in sorted(settings["anchors"]):
        anchor = pd.Timestamp(anchor_text)
        history_start = anchor - pd.Timedelta(days=settings["history_days"])
        label_end = anchor + pd.Timedelta(days=settings["label_days"])
        if history_start < pd.Timestamp(bounds["first"]) or label_end > (
            pd.Timestamp(bounds["last"]) + pd.Timedelta(hours=1)
        ):
            raise ValueError("A future-label cohort is not fully observed")
        cohort = read_source_frame(
            settings,
            sql,
            {
                "history_start": str(history_start),
                "anchor": str(anchor),
                "label_end": str(label_end),
            },
        )
        cohort["anchor"] = anchor_text
        summaries.append(
            {
                "anchor": anchor_text,
                "history_start": str(history_start),
                "label_end_exclusive": str(label_end),
                "users": len(cohort),
                "positive_users": int(cohort["target"].sum()),
                "negative_users": int((cohort["target"] == 0).sum()),
                "positive_share": float(cohort["target"].mean()),
            }
        )
        for feature in ("pv", "cart", "fav", "events", "event_keys"):
            edges = (
                [0, 1, 5, 20, 50, 100, 300, 1000, 3000, 10000, float("inf")]
                if feature in ("pv", "events", "event_keys")
                else [0, 1, 2, 5, 10, 20, 50, 100, 300, float("inf")]
            )
            bins = summarize_bins(cohort, feature, "target", edges)
            bins["anchor"] = anchor_text
            relationships.append(bins)
        latest = cohort
    return {
        "cohort_summary": pd.DataFrame(summaries),
        "forward_associations": pd.concat(relationships, ignore_index=True),
        "latest_cohort": latest,
    }


def _transition_tables(settings: EDASettings) -> dict[str, pd.DataFrame]:
    """Estimate co-presence transitions between successive observed active hours.

    Args:
        settings: Configuration with the maximum allowed inter-hour gap.

    Returns:
        Conditional probabilities, row supports and observation-boundary counts.

    Notes:
        Hours contain multiple behaviors; rows are not categorical probabilities
        summing to one. Last observations are censored, not observed exits.
    """
    hours = read_source_frame(
        settings,
        "SELECT user_id, event_time, pv_count, cart_count,"
        + " fav_count, buy_count FROM user_hour_stats ORDER BY user_id, event_time",
    )
    present = hours[[name + "_count" for name in BEHAVIORS]].gt(0)
    present.columns = list(BEHAVIORS)
    next_present = present.shift(-1, fill_value=False)
    gap = (
        pd.to_datetime(hours["event_time"]).shift(-1)
        - pd.to_datetime(hours["event_time"])
    ).dt.total_seconds() / 3600
    same_user = hours["user_id"].eq(hours["user_id"].shift(-1))
    keep = same_user & gap.gt(0) & gap.le(settings["transition_max_gap_hours"])
    rows = []
    for origin in BEHAVIORS:
        eligible = keep & present[origin]
        support = int(eligible.sum())
        for destination in BEHAVIORS:
            hits = int((eligible & next_present[destination]).sum())
            rows.append(
                {
                    "origin": origin,
                    "destination": destination,
                    "support": support,
                    "next_hour_present": hits,
                    "probability": hits / support if support else float("nan"),
                }
            )
    boundary = pd.DataFrame(
        [
            {
                "active_user_hours": len(hours),
                "multiple_behavior_hours": int(present.sum(axis=1).gt(1).sum()),
                "successive_pairs": int(same_user.sum()),
                "pairs_within_gap": int(keep.sum()),
                "pairs_over_gap": int((same_user & ~keep).sum()),
                "last_user_hours_censored": int((~same_user).sum()),
                "maximum_gap_hours": settings["transition_max_gap_hours"],
            }
        ]
    )
    return {"hour_transitions": pd.DataFrame(rows), "transition_boundary": boundary}


def _reuse_strict_funnel(metadata: dict[str, Any]) -> pd.DataFrame:
    """Reuse a complete one-row SQL result only after checking source and SQL hashes.

    Args:
        metadata: Current EDA source fingerprint.

    Returns:
        The previously fully executed strict seven-day funnel counts.

    Raises:
        ValueError: The source, query or complete-result contract does not match.
    """
    path = PROJECT_ROOT / "outputs/reports/stage2_step1_20261024/sql_analysis.json"
    report = json.loads(path.read_text())
    query = next(row for row in report["queries"] if row["name"] == "strict_funnel")
    query_sha = hashlib.sha256(
        (PROJECT_ROOT / "sql/queries/strict_funnel.sql").read_bytes()
    ).hexdigest()
    if (
        report["database_sha256"] != metadata["source_sha256"]
        or query["query_sha256"] != query_sha
        or query["rows"] != 1
        or len(query["preview"]) != 1
    ):
        raise ValueError("Previously saved funnel is not valid for the current source")
    return pd.DataFrame(query["preview"])


def collect_eda(
    settings: EDASettings, metadata: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    """Collect full-period descriptions and leakage-aware prospective associations.

    Args:
        settings: Validated EDA configuration.
        metadata: Full source fingerprint and cache controls.

    Returns:
        Core metrics and complete analytical tables. User-level tables stay local.

    Raises:
        ValueError: Aggregation counts disagree across data layers.
    """
    tables = _base_tables(settings)
    users = tables["users"]
    branch_sql = (PROJECT_ROOT / "sql/eda/branch_funnels.sql").read_text()
    tables["branch_funnels"] = read_source_frame(
        settings,
        branch_sql,
        {
            "start_time": tables["hours"]["event_time"].min(),
            "end_time": str(
                pd.Timestamp(tables["hours"]["event_time"].max())
                + pd.Timedelta(hours=1)
            ),
            "window_days": 7,
        },
    )
    tables.update(_future_tables(settings))
    tables.update(_transition_tables(settings))
    tables.update(entity_tables(settings, tables))
    tables.update(preference_tables(settings, users))
    source_controls = read_source_frame(
        settings,
        "SELECT COUNT(*) AS active_hours,"
        + " SUM(raw_record_count) AS events,"
        + " SUM(distinct_item_behavior_count) AS event_keys,"
        + " SUM(pv_count) AS pv, SUM(cart_count) AS cart,"
        + " SUM(fav_count) AS fav, SUM(buy_count) AS buy"
        + " FROM user_hour_stats",
    ).iloc[0]
    observed = {
        "active_hours": int(tables["hours"]["active_users"].sum()),
        "events": int(users["events"].sum()),
        "event_keys": int(tables["behavior_sensitivity"]["four_tuple_keys"].sum()),
        **{name: int(users[name].sum()) for name in BEHAVIORS},
    }
    tables["count_controls"] = pd.DataFrame(
        [
            {
                "metric": name,
                "source_total": int(source_controls[name]),
                "eda_total": total,
                "matches": total == int(source_controls[name]),
            }
            for name, total in observed.items()
        ]
    )
    if not tables["count_controls"]["matches"].all():
        raise ValueError("Independent source controls disagree with EDA summaries")
    tables["strict_funnel"] = _reuse_strict_funnel(metadata)
    users["has_purchase"] = users["buy"].gt(0).astype(int)
    tables["activity_distribution"] = summarize_bins(
        users,
        "events",
        "has_purchase",
        [0, 10, 30, 100, 300, 1000, 3000, 10000, float("inf")],
    )
    tables["purchase_distribution"] = summarize_bins(
        users,
        "buy",
        "has_purchase",
        [0, 1, 2, 5, 10, 20, 50, 100, 300, 1000, float("inf")],
    )
    tables["purchase_day_distribution"] = (
        users.groupby("purchase_days").size().reset_index(name="users")
    )
    cohorts = tables["latest_cohort"]
    high_frequency = cohorts.assign(flagged=cohorts["flagged_hours"].gt(0))
    tables["flagged_cohort_comparison"] = (
        high_frequency.groupby("flagged")
        .agg(
            users=("target", "size"),
            positives=("target", "sum"),
            purchase_rate=("target", "mean"),
            mean_records=("events", "mean"),
            mean_keys=("event_keys", "mean"),
        )
        .reset_index()
    )
    category_count = len(tables["categories"])
    entity_counts = read_cache_frame(
        settings,
        "SELECT COUNT(*) AS items, SUM(view_pairs) AS view_pairs,"
        + " SUM(converted_pairs) AS converted_pairs FROM item_profiles",
    ).iloc[0]
    hours = tables["hours"]
    days = tables["daily"]
    top_fifth = max(1, int(np.ceil(category_count * 0.2)))
    tail = tables["category_tail"]
    metrics = {
        "users": len(users),
        "items": int(entity_counts["items"]),
        "categories": category_count,
        "records": int(users["events"].sum()),
        "four_tuple_keys": int(tables["behavior_sensitivity"]["four_tuple_keys"].sum()),
        "first_hour": hours["event_time"].min(),
        "last_hour": hours["event_time"].max(),
        "calendar_days": len(days),
        "records_per_user": float(users["events"].mean()),
        "items_per_user": float(users["interacted_items"].mean()),
        "categories_per_user": float(users["interacted_categories"].mean()),
        "mean_observed_category_coverage": float(
            users["interacted_categories"].mean() / category_count
        ),
        "active_user_days": int(users["active_days"].sum()),
        "observed_hour_buckets_per_active_user_day": float(
            users["active_hour_buckets"].sum() / users["active_days"].sum()
        ),
        "purchase_users": int(users["has_purchase"].sum()),
        "purchase_user_share": float(users["has_purchase"].mean()),
        "purchase_records": int(users["buy"].sum()),
        "purchase_records_per_user": float(users["buy"].mean()),
        "purchase_record_share": float(users["buy"].sum() / users["events"].sum()),
        "buy_to_pv_record_ratio": float(users["buy"].sum() / users["pv"].sum()),
        "view_pairs": int(entity_counts["view_pairs"]),
        "converted_pairs": int(entity_counts["converted_pairs"]),
        "same_window_pair_purchase_coverage": float(
            entity_counts["converted_pairs"] / entity_counts["view_pairs"]
        ),
        "users_with_multiple_purchase_records": int(users["buy"].ge(2).sum()),
        "users_with_multiple_purchase_days": int(users["purchase_days"].ge(2).sum()),
        "flagged_user_hours": int(hours["flagged_hours"].sum()),
        "flagged_records": int(hours["flagged_records"].sum()),
        "top_20pct_categories_pv_share": float(
            tail.head(top_fifth)["pv"].sum() / tail["pv"].sum()
        ),
        "top_20pct_categories_buy_share": float(
            tail.head(top_fifth)["buy"].sum() / tail["buy"].sum()
        ),
    }
    if metrics["records"] != metadata["controls"]["raw_records"]:
        raise ValueError("User profiles disagree with the full source record count")
    if metrics["four_tuple_keys"] != metadata["controls"]["four_tuple_keys"]:
        raise ValueError("Per-behavior key counts disagree with source controls")
    if int(days["events"].sum()) != metrics["records"]:
        raise ValueError("Daily counts disagree with full-period counts")
    return metrics, tables
