"""Render item, category, duplicate-sensitivity and cohort comparison figures."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from user_behavior_analysis.service.eda_charts import BEHAVIORS
from user_behavior_analysis.service.eda_charts import NAMES
from user_behavior_analysis.service.eda_charts import save_figure


def _entity_rank(frame: pd.DataFrame, kind: str, mode: str, directory: Path) -> None:
    """Plot one Top20 ranking with denominator-aware coverage labels.

    Args:
        frame: Selected entity rows with event and user-item pair counts.
        kind: Item or category name.
        mode: Volume or coverage ordering.
        directory: Figure output directory.
    """
    frame = frame.iloc[::-1]
    labels = frame[kind + "_id"].astype(str)
    if kind == "item":
        labels = labels + " / 类目" + frame["category_id"].astype(str)
    fig, ax = plt.subplots(figsize=(12, 8.8), layout="constrained")
    values = (
        frame["events"] / 1000 if mode == "volume" else frame["coverage_rate"] * 100
    )
    color = "#6d9dbf" if mode == "volume" else "#d69374"
    ax.barh(labels, values, color=color)
    if mode == "coverage":
        lower = values - frame["lower"] * 100
        upper = frame["upper"] * 100 - values
        ax.errorbar(
            values,
            range(len(frame)),
            xerr=np.vstack([lower, upper]),
            fmt="none",
            color="#8e4a30",
            capsize=2,
        )
    for index, (_, row) in enumerate(frame.iterrows()):
        rate = row["converted_pairs"] / row["view_pairs"] if row["view_pairs"] else 0
        note = (
            f"覆盖 {rate:.1%} · 浏览对 n={int(row['view_pairs']):,}"
            if mode == "volume"
            else f"n={int(row['view_pairs']):,}"
        )
        ax.text(values.iloc[index], index, "  " + note, va="center", fontsize=9)
    ax.set_xlim(0, max(float(values.max()) * 1.65, 1))
    ax.set_xlabel(
        "原始行为记录数（千条）"
        if mode == "volume"
        else "同窗浏览用户商品对的购买覆盖率（%）"
    )
    subject = "商品" if kind == "item" else "类目"
    ax.set_title(
        subject
        + (
            " Top20：按交互记录量"
            if mode == "volume"
            else " Top20：按覆盖率 Wilson 下界排名"
        )
    )
    save_figure(fig, directory, kind + "_ranking_" + mode)


def _tail_and_quadrants(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Show full category concentration and adequately supported item quadrants.

    Args:
        tables: Category cumulative shares and local eligible item profiles.
        directory: Figure output directory.
    """
    tail = tables["category_tail"]
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    ax.plot(
        tail["category_share"] * 100,
        tail["cumulative_pv_share"] * 100,
        color="#3777a8",
        linewidth=2,
        label="累计浏览记录占比",
    )
    ax.plot(
        tail["category_share"] * 100,
        tail["cumulative_buy_share"] * 100,
        color="#d65f38",
        linewidth=2,
        label="累计购买记录占比",
    )
    ax.plot([0, 100], [0, 100], color="#aeb9c1", linestyle="--", label="均匀分布参考")
    ax.axvline(20, color="#9aaaba", linestyle=":")
    ax.set_xlabel("按浏览量降序排列的类目累计占比（%）")
    ax.set_ylabel("累计记录占比（%）")
    ax.set_title("类目长尾与流量集中度")
    ax.legend(loc="lower right")
    save_figure(fig, directory, "category_long_tail")
    items = tables["item_quadrants"]
    thresholds = tables["quadrant_thresholds"].iloc[0]
    fig, ax = plt.subplots(figsize=(10, 5.5), layout="constrained")
    image = ax.hexbin(
        items["pv"],
        items["smoothed_coverage"] * 100,
        xscale="log",
        gridsize=40,
        mincnt=1,
        bins="log",
        cmap="YlOrRd",
    )
    ax.axvline(thresholds["pv_record_median"], color="#526b80", linestyle="--")
    ax.axhline(thresholds["coverage_prior"] * 100, color="#526b80", linestyle="--")
    ax.set_xlabel("浏览记录数（对数；无真实曝光字段）")
    ax.set_ylabel("平滑后的同窗购买覆盖率（%）")
    ax.set_title(f"商品浏览—购买覆盖四象限：{len(items):,}个有足够观察的商品")
    fig.colorbar(image, ax=ax, label="六边形内商品数（对数色阶）")
    save_figure(fig, directory, "item_quadrants")


def _preferences_and_sensitivity(
    tables: dict[str, pd.DataFrame], directory: Path
) -> None:
    """Plot comparable category shares and raw-versus-key record totals.

    Args:
        tables: Aggregated preference and duplicate-sensitivity results.
        directory: Figure output directory.
    """
    prefs = tables["preference_shared"]
    ordered = (
        prefs.groupby("category_id")["event_keys"]
        .sum()
        .sort_values(ascending=False)
        .index
    )
    matrix = (
        prefs.pivot(index="activity", columns="category_id", values="event_keys_share")
        .reindex(index=["低活跃", "中活跃", "高活跃"], columns=ordered)
        .fillna(0)
        * 100
    )
    fig, ax = plt.subplots(figsize=(13, 3.5), layout="constrained")
    image = ax.imshow(matrix, aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(3), matrix.index)
    ax.set_xticks(range(len(ordered)), ordered)
    for row_index in range(3):
        for column in range(len(ordered)):
            ax.text(
                column,
                row_index,
                f"{matrix.iloc[row_index, column]:.1f}%",
                ha="center",
                va="center",
                fontsize=9,
            )
    ax.set_xlabel("共同展示的热门类目 ID（每组Top5另见统计表）")
    ax.set_title("活跃度 × 类目偏好：类目四元组计数占该层全部计数的比例")
    fig.colorbar(image, ax=ax, label="层内四元组计数占比（%）")
    save_figure(fig, directory, "activity_category_preferences")
    data = tables["behavior_sensitivity"].set_index("behavior").loc[list(BEHAVIORS)]
    positions = np.arange(4)
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    ax.bar(
        positions - 0.18,
        data["raw_records"],
        0.36,
        label="原始有效记录",
        color="#79a4c3",
    )
    ax.bar(
        positions + 0.18,
        data["four_tuple_keys"],
        0.36,
        label="四元组计数",
        color="#d69374",
    )
    ax.set_yscale("log")
    ax.set_xticks(positions, [NAMES[name] for name in BEHAVIORS])
    ax.set_ylabel("记录 / 四元组数量（对数）")
    ax.set_title("计数口径敏感性：不据此认定额外记录为错误")
    ax.legend()
    for position, (_, row) in zip(positions, data.iterrows()):
        ax.text(
            float(position),
            row["raw_records"] * 1.2,
            f"原始 / 四元组 = {row['raw_records'] / row['four_tuple_keys']:.2f}",
            ha="center",
            fontsize=10,
        )
    ax.set_ylim(10000, float(data["raw_records"].max()) * 3)
    save_figure(fig, directory, "duplicate_sensitivity")


def _cohorts_and_paths(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Contrast complete future-label cohorts and overlapping purchase paths.

    Args:
        tables: Three cohort supports and common-denominator path counts.
        directory: Figure output directory.
    """
    cohorts = tables["cohort_summary"]
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    ax.bar(
        cohorts["anchor"],
        cohorts["negative_users"],
        color="#7ca4c1",
        label="未来7天未观测到购买",
    )
    ax.bar(
        cohorts["anchor"],
        cohorts["positive_users"],
        bottom=cohorts["negative_users"],
        color="#d69374",
        label="未来7天观测到购买",
    )
    for index, (_, row) in enumerate(cohorts.iterrows()):
        ax.text(
            index,
            row["users"] + 100,
            f"n={int(row['users']):,} · 正例 {row['positive_share']:.1%}",
            ha="center",
        )
    ax.set_ylim(0, float(cohorts["users"].max()) * 1.18)
    ax.set_ylabel("历史7天活跃用户数")
    ax.set_xlabel("预测截点（标签从该日00:00开始）")
    ax.set_title("未来7天用户级正负样本比例：不同时间窗口")
    ax.legend(loc="lower right")
    save_figure(fig, directory, "forward_cohort_balance")
    row = tables["branch_funnels"].iloc[0]
    strict = tables["strict_funnel"].iloc[0]
    names = [
        "浏览→购买（同小时允许，候选）",
        "浏览→购买（严格跨小时）",
        "浏览→加购→购买（严格跨小时）",
        "浏览→收藏→购买（严格跨小时）",
        "浏览→加购→收藏→购买（严格跨小时）",
    ]
    counts = [
        row["pv_buy_same_hour_compatible"],
        row["pv_buy_cross_hour"],
        row["pv_cart_buy_cross_hour"],
        row["pv_fav_buy_cross_hour"],
        strict["purchase_pairs"],
    ]
    fig, ax = plt.subplots(figsize=(12, 4.8), layout="constrained")
    rates = np.array(counts) / row["eligible_view_pairs"] * 100
    ax.barh(names[::-1], rates[::-1], color="#d69374")
    for index, rate, count in zip(range(5), rates[::-1], counts[::-1]):
        ax.text(rate, index, f"  {int(count):,} 对 · {rate:.3f}%", va="center")
    ax.set_xlim(0, max(rates) * 1.6)
    ax.set_xlabel("占相同完整7天随访浏览用户商品对的比例（%）")
    ax.set_title("替代购买路径对比（路径重叠，不是可相加的漏斗阶段）")
    save_figure(fig, directory, "alternative_purchase_paths")


def render_entity_charts(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Render entity, preference, counting and cohort comparison figures.

    Args:
        tables: Complete analytical frames; item-level frames stay local.
        directory: Project report figure directory.
    """
    for kind, prefix in (("category", "categories"), ("item", "items")):
        for mode in ("volume", "coverage"):
            _entity_rank(tables["top_" + prefix + "_" + mode], kind, mode, directory)
    _tail_and_quadrants(tables, directory)
    _preferences_and_sensitivity(tables, directory)
    _cohorts_and_paths(tables, directory)
