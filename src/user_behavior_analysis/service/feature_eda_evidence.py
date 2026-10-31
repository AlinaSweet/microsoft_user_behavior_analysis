"""Connect completed feature tables to deeper EDA and data-limit diagnostics."""

import json
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.eda_charts import configure_eda_plots
from user_behavior_analysis.service.eda_charts import save_figure

SEGMENTS = {
    "high_value_proxy": "高价值代理",
    "potential_proxy": "潜力代理",
    "at_risk_proxy": "近期风险代理",
    "dormant_proxy": "沉睡代理",
}


def _rf_and_coverage(settings: FeatureSettings) -> dict[str, Any]:
    """Compare produced RF proxies, mature future outcomes and latent coverage.

    Args:
        settings: Completed snapshots and EDA destinations.

    Returns:
        Segment counts, future purchase proportions and representation coverage.
    """
    segment_rows = []
    latent_rows = []
    latest_users = pd.DataFrame()
    for anchor in settings.options["anchors"]:
        directory = settings.output_dir / "snapshots" / anchor
        users = pd.read_parquet(directory / "user_features.parquet")
        targets = pd.read_parquet(directory / "user_targets.parquet")
        joined = users.merge(
            targets[["user_id", "target", "target_available"]],
            on="user_id",
            validate="one_to_one",
        )
        for segment, frame in joined.groupby("user_rf_segment"):
            segment_rows.append(
                {
                    "anchor": anchor,
                    "segment": str(segment),
                    "users": len(frame),
                    "future_label_available": bool(frame["target_available"].all()),
                    "future_purchase_share": (
                        float(frame["target"].mean())
                        if frame["target_available"].all()
                        else None
                    ),
                    "mean_raw_records_7d": float(frame["user_event_count_7d"].mean()),
                    "mean_key_count_7d": float(frame["user_key_count_7d"].mean()),
                }
            )
        state = json.loads((directory / "completion.json").read_text())
        cov = state["latent_coverage"]
        latent_rows.append(
            {
                "anchor": anchor,
                "svd_available_pair_share": cov["available_candidate_pairs"]
                / cov["candidate_pairs"],
                "graph_known_pair_share": 1
                - next(
                    row
                    for row in state["quality"]
                    if row["name"] == "pair_cooc_graph_known"
                )["zero_rate"],
            }
        )
        latest_users = users
    segments = pd.DataFrame(segment_rows)
    coverage = pd.DataFrame(latent_rows)
    figures = settings.eda_report_dir / "figures"
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), layout="constrained")
    counts = segments.pivot(index="anchor", columns="segment", values="users").fillna(0)
    counts.rename(columns=SEGMENTS).plot.bar(
        stacked=True, ax=axes[0], color=["#91b2c9", "#d59b77", "#a68fb5", "#d4bc70"]
    )
    axes[0].set_title("RF与最近活跃代理分群")
    axes[0].get_legend().set_title("代理群体")
    axes[0].set_ylabel("历史已观测用户数")
    axes[0].set_xlabel("截点")
    axes[0].tick_params(axis="x", rotation=0)
    for segment, label in SEGMENTS.items():
        selected = segments.loc[
            (segments["segment"] == segment) & segments["future_label_available"]
        ]
        axes[1].plot(
            selected["anchor"],
            selected["future_purchase_share"] * 100,
            marker="o",
            label=label,
        )
    axes[1].set_title("各代理群体的未来7天购买比例")
    axes[1].set_ylabel("用户比例（%）；无金额，非完整金额RFM")
    axes[1].legend(fontsize=9)
    save_figure(fig, figures, "rf_proxy_segments")
    fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
    ax.plot(
        coverage["anchor"],
        coverage["svd_available_pair_share"] * 100,
        marker="o",
        label="冻结SVD可用候选对",
        color="#d65f38",
    )
    ax.plot(
        coverage["anchor"],
        coverage["graph_known_pair_share"] * 100,
        marker="o",
        label="有训练支持的共现图候选对",
        color="#3777a8",
    )
    ax.set_ylim(0, 105)
    ax.set_xlabel("截点；11月25日前拟合，后续不读未来重拟合")
    ax.set_ylabel("候选对覆盖比例（%）")
    ax.set_title("高级特征覆盖范围：未知商品必须显式标记")
    ax.legend()
    save_figure(fig, figures, "latent_feature_coverage")
    columns = [
        "user_event_count_1d",
        "user_event_count_7d",
        "user_key_count_7d",
        "user_active_days_7d",
        "user_recency_hours",
        "user_buy_key_count_7d",
        "user_cart_key_count_7d",
        "user_fav_key_count_7d",
        "user_category_entropy_7d",
        "user_top_category_key_share_7d",
        "user_max_active_streak_7d",
        "user_flagged_hour_count_7d",
    ]
    corr = latest_users[columns].corr()
    fig, ax = plt.subplots(figsize=(11, 8), layout="constrained")
    short = [
        "1日记录",
        "7日记录",
        "7日四元组",
        "活跃天数",
        "最近活跃间隔",
        "购买键数",
        "加购键数",
        "收藏键数",
        "类目熵",
        "首选类目份额",
        "最长活跃连续天",
        "高频小时数",
    ]
    ax.set_xticks(range(len(short)), short, rotation=45, ha="right")
    ax.set_yticks(range(len(short)), short)
    ax.set_title("候选特征之间的相关性（2025-12-19，非最终筛选）")
    fig.colorbar(
        ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1),
        ax=ax,
        label="Pearson相关系数；成对非空观测",
    )
    save_figure(fig, figures, "candidate_feature_correlations")
    return {
        "segments": json.loads(segments.to_json(orient="records")),
        "latent_coverage": json.loads(coverage.to_json(orient="records")),
        "correlation_features": columns,
        "correlations": json.loads(corr.reset_index().to_json(orient="records")),
    }


def _category_cycles(settings: FeatureSettings) -> dict[str, Any]:
    """Estimate mature strict-hour view-to-buy delays and cross-date repeat proxies.

    Args:
        settings: Complete-record key source and report destination.

    Returns:
        Category-level mature cohort supports and observed delay/repeat statistics.
    """
    path = settings.base_dir / "key_hour/data.parquet"
    database = PROJECT_ROOT / ".cache/feature_system/eda_cycles.duckdb"
    database.parent.mkdir(parents=True, exist_ok=True)
    with feature_connection(settings, database) as connection:
        connection.read_parquet(str(path)).create_view("k")
        connection.execute(
            (
                "CREATE OR REPLACE TABLE mature_views AS "
                + "SELECT user_id,item_id,category_id,"
            )
            + "MIN(event_time) AS first_pv FROM k WHERE behavior_type=1"
            + " GROUP BY user_id,item_id,category_id"
            + " HAVING MIN(event_time)<=TIMESTAMP '2025-12-12 00:00:00'"
        )
        connection.execute(
            "CREATE OR REPLACE TABLE purchases_after_view AS"
            + " SELECT v.user_id,v.item_id,v.category_id,v.first_pv,"
            + " MIN(k.event_time) AS first_buy FROM mature_views v JOIN k"
            + " ON v.user_id=k.user_id AND v.item_id=k.item_id"
            + " WHERE k.behavior_type=4 AND k.event_time>v.first_pv"
            + " AND k.event_time<v.first_pv+INTERVAL 7 DAY"
            + " GROUP BY v.user_id,v.item_id,v.category_id,v.first_pv"
        )
        cycles = connection.execute(
            "WITH c AS(SELECT category_id,COUNT(*) AS purchased_pairs,"
            + " median(date_diff('hour',first_pv,first_buy)) AS median_gap_hours,"
            + (
                " quantile_cont(date_diff('hour',first_pv"
                + ",first_buy),0.9) AS p90_gap_hours"
            )
            + " FROM purchases_after_view GROUP BY category_id),v AS("
            + "SELECT category_id,COUNT(*) AS eligible_view_pairs FROM mature_views"
            + " GROUP BY category_id) SELECT v.*,COALESCE(c.purchased_pairs,0)"
            + " AS purchased_pairs,c.median_gap_hours,c.p90_gap_hours,"
            + " COALESCE(c.purchased_pairs,0)::DOUBLE/v.eligible_view_pairs AS coverage"
            + " FROM v LEFT JOIN c USING(category_id)"
        ).df()
        repeats = connection.execute(
            "WITH dates AS(SELECT DISTINCT user_id,item_id,category_id,"
            + "CAST(event_time AS DATE) AS buy_date FROM k WHERE behavior_type=4),"
            + "f AS(SELECT user_id,item_id,category_id,MIN(buy_date) AS first_date"
            + " FROM dates GROUP BY user_id,item_id,category_id"
            + " HAVING MIN(buy_date)<=DATE '2025-12-11'),r AS(SELECT f.*,"
            + " MIN(d.buy_date) AS repeat_date FROM f LEFT JOIN dates d"
            + " ON f.user_id=d.user_id AND f.item_id=d.item_id"
            + " AND d.buy_date>f.first_date AND d.buy_date<=f.first_date+7"
            + " GROUP BY f.user_id,f.item_id,f.category_id,f.first_date)"
            + " SELECT category_id,COUNT(*) AS eligible_purchase_pairs,"
            + " COUNT(repeat_date) AS repeated_pairs,"
            + " COUNT(repeat_date)::DOUBLE/COUNT(*) AS repeat_proxy_share"
            + " FROM r GROUP BY category_id"
        ).df()
    figures = settings.eda_report_dir / "figures"
    supported = cycles.loc[cycles["purchased_pairs"] >= 20].nlargest(
        20, "eligible_view_pairs"
    )
    fig, ax = plt.subplots(figsize=(11, 7), layout="constrained")
    selected = supported.iloc[::-1]
    ax.barh(selected["category_id"], selected["median_gap_hours"], color="#7da6c3")
    ax.set_xlabel("浏览后第一次可确认跨小时购买的间隔中位数（小时）")
    ax.set_title("有完整7天随访的类目转化间隔；仅展示购买对数≥20")
    save_figure(fig, figures, "category_purchase_delays")
    selected = (
        repeats.loc[repeats["eligible_purchase_pairs"] >= 50]
        .nlargest(20, "eligible_purchase_pairs")
        .iloc[::-1]
    )
    fig, ax = plt.subplots(figsize=(11, 7), layout="constrained")
    ax.barh(
        selected["category_id"], selected["repeat_proxy_share"] * 100, color="#d59576"
    )
    ax.set_xlabel("首购日期后1至7个自然日再次观测购买的用户商品对占比（%）")
    ax.set_title("类目跨日期复购代理：完整随访，非订单复购")
    save_figure(fig, figures, "category_repeat_proxies")
    return {
        "cycles": json.loads(cycles.to_json(orient="records")),
        "repeat_proxies": json.loads(repeats.to_json(orient="records")),
        "mature_view_pairs": int(cycles["eligible_view_pairs"].sum()),
        "cross_hour_purchase_pairs": int(cycles["purchased_pairs"].sum()),
        "interpretation": (
            "strict cross-hour conditional observed d" + "elays; date-repeat proxy"
        ),
    }


def extend_feature_eda(settings: FeatureSettings) -> dict[str, Any]:
    """Add production-feature evidence and mature category analysis to the EDA report.

    Args:
        settings: Completed feature snapshots and exploration directories.

    Returns:
        RF groups, coverage, feature associations and category lifecycle evidence.
    """
    configure_eda_plots()
    feature_evidence = _rf_and_coverage(settings)
    category_evidence = _category_cycles(settings)
    result = {
        "feature_evidence": feature_evidence,
        "category_evidence": category_evidence,
        "calendar": {
            "observed_start": "2025-11-18",
            "observed_end": "2025-12-18",
            "public_holiday_days": 0,
            "source": "https://www.gov.cn/zhengce/zhengceku/202411/content_6986383.htm",
            "holiday_contrast": (
                "unavailable: no public-holiday group in " + "observation window"
            ),
        },
        "limits": [
            "no amounts or orders",
            "unknown within-hour sequence",
            "short observed history",
            "frozen latent coverage is incomplete",
        ],
    }
    write_json(settings.eda_report_dir / "feature_evidence.json", result)
    return result
