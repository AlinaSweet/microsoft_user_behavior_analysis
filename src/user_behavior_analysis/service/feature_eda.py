"""Deepen exploratory evidence before designing the new feature intermediates."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.eda_charts import configure_eda_plots
from user_behavior_analysis.service.eda_charts import save_figure


def _read_eda_source(
    settings: FeatureSettings, sql: str, params: dict[str, Any]
) -> pd.DataFrame:
    """Read bounded EDA groups through a read-only source connection.

    Args:
        settings: Feature and EDA source locations.
        sql: Fixed SELECT statement.
        params: Named parameter values.

    Returns:
        Complete small analytical groups.
    """
    with closing(
        sqlite3.connect(settings.source_database.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.execute("PRAGMA query_only = ON")
        return pd.read_sql_query(sql, connection, params=params)


def _conditional_groups(
    cohort: pd.DataFrame, anchor: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare behavioral associations within comparable activity and purchase strata.

    Args:
        cohort: One history-only feature and future-outcome cohort.
        anchor: Observation boundary identifying the independent time view.

    Returns:
        Stratum-specific counts and support-aware standardized contrasts.

    Notes:
        Strata improve comparability without establishing causality.
    """
    frame = cohort.copy()
    frame["activity_band"] = pd.qcut(
        frame["events"], 5, labels=False, duplicates="drop"
    ).astype(int)
    frame["past_purchase"] = frame["buy"].gt(0)
    rows = []
    adjusted = []
    for feature in ("cart", "fav", "flagged_hours"):
        frame["exposed"] = frame[feature].gt(0)
        groups = (
            frame.groupby(["activity_band", "past_purchase", "exposed"])["target"]
            .agg(users="size", positives="sum")
            .reset_index()
        )
        groups["rate"] = groups["positives"] / groups["users"]
        groups["feature"] = feature
        groups["anchor"] = anchor
        rows.append(groups)
        weights = (
            frame.groupby(["activity_band", "past_purchase"])
            .size()
            .rename("population")
        )
        compared = groups.pivot(
            index=["activity_band", "past_purchase"],
            columns="exposed",
            values=["users", "rate"],
        )
        compared[("population", "all")] = weights
        if False not in compared["users"] or True not in compared["users"]:
            continue
        valid = compared.loc[
            compared["users"][False].ge(30) & compared["users"][True].ge(30)
        ]
        mass = valid[("population", "all")].sum()
        if mass == 0:
            continue
        low = float((valid["rate"][False] * valid[("population", "all")]).sum() / mass)
        high = float((valid["rate"][True] * valid[("population", "all")]).sum() / mass)
        adjusted.append(
            {
                "anchor": anchor,
                "feature": feature,
                "eligible_strata": len(valid),
                "population_coverage": float(mass / len(frame)),
                "unexposed_standardized_rate": low,
                "exposed_standardized_rate": high,
                "difference_percentage_points": (high - low) * 100,
                "method": "direct standardization; >=30 users per exposure arm/stratum",
            }
        )
    return pd.concat(rows, ignore_index=True), pd.DataFrame(adjusted)


def _rank_sensitivity() -> tuple[dict[str, Any], pd.DataFrame]:
    """Compare full-period user ranks without deleting any observed records.

    Returns:
        Rank correlations, top-decile overlap and user-level rank changes.
    """
    source = PROJECT_ROOT / "data/processed/eda_dashboard1_20261029/users.parquet"
    users = pd.read_parquet(source)
    users["keys"] = users[["pv_keys", "fav_keys", "cart_keys", "buy_keys"]].sum(axis=1)
    users["raw_rank"] = users["events"].rank(method="average", ascending=False)
    users["key_rank"] = users["keys"].rank(method="average", ascending=False)
    raw_top = set(users.nlargest(1000, "events")["user_id"])
    key_top = set(users.nlargest(1000, "keys")["user_id"])
    report = {
        "users": len(users),
        "raw_key_spearman": float(users["raw_rank"].corr(users["key_rank"])),
        "raw_hour_spearman": float(
            users["events"].corr(users["active_hour_buckets"], method="spearman")
        ),
        "top_decile_overlap_users": len(raw_top & key_top),
        "top_decile_overlap_share": len(raw_top & key_top) / 1000,
        "median_absolute_rank_change": float(
            (users["raw_rank"] - users["key_rank"]).abs().median()
        ),
    }
    return report, users


def _draw_extension(
    conditional: pd.DataFrame,
    adjusted: pd.DataFrame,
    users: pd.DataFrame,
    directory: Path,
) -> None:
    """Visualize conditional associations and raw-versus-key rank stability.

    Args:
        conditional: Stratum-level binary exposure results.
        adjusted: Directly standardized contrasts.
        users: Local user-level count ranks.
        directory: Figure output location.
    """
    configure_eda_plots()
    latest = sorted(conditional["anchor"].unique())[-1]
    data = conditional.loc[
        (conditional["anchor"] == latest) & ~conditional["past_purchase"]
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), layout="constrained")
    for ax, feature, label in zip(axes, ("cart", "fav"), ("历史加购", "历史收藏")):
        selected = data.loc[data["feature"] == feature]
        for exposed, color in ((False, "#3777a8"), (True, "#d65f38")):
            cells = selected.loc[selected["exposed"] == exposed]
            ax.plot(
                cells["activity_band"] + 1,
                cells["rate"] * 100,
                marker="o",
                color=color,
                label=label + ("有" if exposed else "无"),
            )
        ax.set_xticks(range(1, 6))
        ax.set_xlabel("历史总活跃度五分层（1低，5高）")
        ax.set_ylabel("未来7天购买用户占比（%）")
        ax.set_title(label + "：历史7天无购买人群")
        ax.legend()
    fig.suptitle(latest + " 截点：在相似活跃度内比较", fontsize=16)
    save_figure(fig, directory, "activity_controlled_intent")
    fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
    for feature, label, color in (
        ("cart", "加购", "#d09a32"),
        ("fav", "收藏", "#8e76a6"),
        ("flagged_hours", "高频小时标记", "#3777a8"),
    ):
        cells = adjusted.loc[adjusted["feature"] == feature]
        ax.plot(
            cells["anchor"],
            cells["difference_percentage_points"],
            label=label,
            marker="o",
            color=color,
        )
    ax.axhline(0, color="#9aaaba", linestyle="--")
    ax.set_ylabel("标准化后有/无该行为的未来购买比例差（百分点）")
    ax.set_xlabel("截点；使用共同活跃度×历史购买层权重")
    ax.set_title("分层后的行为关联是否跨时间稳定？（描述性比较）")
    ax.legend()
    save_figure(fig, directory, "standardized_intent_contrasts")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    image = axes[0].hexbin(
        users["raw_rank"],
        users["key_rank"],
        gridsize=55,
        bins="log",
        mincnt=1,
        cmap="YlOrRd",
    )
    axes[0].plot([0, 10000], [0, 10000], color="#9aaaba", linestyle="--")
    axes[0].set_xlabel("原始次数排名")
    axes[0].set_ylabel("四元组次数排名")
    axes[0].set_title("同一用户在两种计数下的活跃度排名")
    fig.colorbar(image, ax=axes[0], label="用户数（对数色阶）")
    axes[1].hist(
        (users["raw_rank"] - users["key_rank"]).abs(), bins=40, color="#7da6c3"
    )
    axes[1].set_xlabel("绝对排名变化")
    axes[1].set_ylabel("用户数")
    axes[1].set_title("重复计数对排名的影响分布")
    save_figure(fig, directory, "duplicate_rank_sensitivity")


def run_feature_eda(settings: FeatureSettings) -> dict[str, Any]:
    """Finish the deeper EDA evidence used to justify intermediate-table design.

    Args:
        settings: Validated feature and EDA report configuration.

    Returns:
        Cohort-specific standardized associations and rank sensitivity evidence.
    """
    directory = settings.eda_report_dir
    directory.mkdir(parents=True, exist_ok=True)
    sql = (PROJECT_ROOT / "sql/eda/forward_user_cohort.sql").read_text()
    conditional_frames = []
    adjusted_frames = []
    for anchor in settings.options["anchors"]:
        if anchor == max(settings.options["anchors"]):
            continue
        timestamp = pd.Timestamp(anchor)
        cohort = _read_eda_source(
            settings,
            sql,
            {
                "anchor": str(timestamp),
                "history_start": str(timestamp - pd.Timedelta(days=7)),
                "label_end": str(timestamp + pd.Timedelta(days=7)),
            },
        )
        conditional, adjusted = _conditional_groups(cohort, anchor)
        conditional_frames.append(conditional)
        adjusted_frames.append(adjusted)
    conditional = pd.concat(conditional_frames, ignore_index=True)
    adjusted = pd.concat(adjusted_frames, ignore_index=True)
    ranks, users = _rank_sensitivity()
    _draw_extension(conditional, adjusted, users, directory / "figures")
    users[["user_id", "raw_rank", "key_rank"]].to_parquet(
        settings.output_dir / "eda_user_ranks.parquet", index=False
    )
    result = {
        "rank_sensitivity": ranks,
        "conditional_associations": json.loads(conditional.to_json(orient="records")),
        "standardized_associations": json.loads(adjusted.to_json(orient="records")),
        "causal_interpretation": False,
        "source_scope": "all valid original records; no deletion",
    }
    write_json(directory / "analysis.json", result)
    return result
