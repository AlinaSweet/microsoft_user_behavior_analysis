"""Render reproducible standalone EDA figures with explicit units and time windows."""

from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.figure import Figure

BEHAVIORS = ("pv", "cart", "fav", "buy")
NAMES = {"pv": "浏览", "cart": "加购", "fav": "收藏", "buy": "购买"}
COLORS = {"pv": "#3777a8", "cart": "#d09a32", "fav": "#8e76a6", "buy": "#d65f38"}


def configure_eda_plots() -> None:
    """Select a headless backend, available Chinese font and readable defaults."""
    matplotlib.use("Agg")
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if path.exists():
            font_manager.fontManager.addfont(str(path))
            name = font_manager.FontProperties(fname=str(path)).get_name()
            plt.rcParams["font.family"] = name
            break
    plt.rcParams.update(
        {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.titlesize": 15,
            "font.size": 11,
            "axes.labelcolor": "#35485a",
            "text.color": "#1b3043",
            "axes.edgecolor": "#c8d2da",
            "grid.alpha": 0.2,
            "savefig.facecolor": "white",
        }
    )


def save_figure(fig: Figure, directory: Path, name: str) -> None:
    """Export matching PNG and SVG files and release the figure.

    Args:
        fig: Complete Matplotlib figure.
        directory: Project report figure directory.
        name: Lowercase output stem.
    """
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / (name + ".png"), dpi=160, bbox_inches="tight")
    fig.savefig(directory / (name + ".svg"), bbox_inches="tight")
    plt.close(fig)


def _heatmaps(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Render weekday-normalized activity and purchase-share heatmaps.

    Args:
        tables: Analytical tables including all 744 source hours.
        directory: Figure output directory.
    """
    hours = tables["hours"]
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for behavior in ("events",) + BEHAVIORS:
        values = hours.groupby(["weekday", "hour"])[behavior].mean().unstack()
        fig, ax = plt.subplots(figsize=(13, 4.2), layout="constrained")
        image = ax.imshow(values.reindex(range(7)), aspect="auto", cmap="YlOrRd")
        ax.set_xticks(range(24), [str(hour) for hour in range(24)])
        ax.set_yticks(range(7), weekdays)
        ax.set_xlabel("源小时（按 Asia/Shanghai 假设解释）")
        title = "全部行为" if behavior == "events" else NAMES[behavior]
        ax.set_title(title + "：星期 × 小时的日均记录量")
        fig.colorbar(image, ax=ax, label="同一星期小时的平均记录数")
        save_figure(fig, directory, "heatmap_" + behavior)
    grouped = hours.groupby(["weekday", "hour"])[["buy_users", "active_users"]].sum()
    values = (grouped["buy_users"] / grouped["active_users"]).unstack() * 100
    fig, ax = plt.subplots(figsize=(13, 4.2), layout="constrained")
    image = ax.imshow(values.reindex(range(7)), aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(24), [str(hour) for hour in range(24)])
    ax.set_yticks(range(7), weekdays)
    ax.set_xlabel("小时")
    ax.set_title("小时桶内购买用户占活跃用户比例（并非浏览后转化率）")
    fig.colorbar(image, ax=ax, label="购买活跃用户占比（%）")
    save_figure(fig, directory, "heatmap_purchase_share")


def _daily_and_distribution(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Plot daily trends, user activity and purchase-record distributions.

    Args:
        tables: Daily summaries and user profiles.
        directory: Figure output directory.
    """
    daily = tables["daily"]
    dates = pd.to_datetime(daily["event_date"])
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True, layout="constrained")
    for behavior in BEHAVIORS:
        axes[0].plot(
            dates,
            daily[behavior],
            label=NAMES[behavior],
            color=COLORS[behavior],
            linewidth=2,
        )
    axes[0].set_yscale("log")
    axes[0].set_ylabel("行为记录数（对数）")
    axes[0].set_title("每日四类行为趋势与购买用户占比")
    axes[0].legend(ncol=4)
    axes[1].plot(
        dates,
        daily["purchase_user_share"] * 100,
        color=COLORS["buy"],
        marker="o",
        markersize=3,
    )
    axes[1].set_ylabel("购买用户 / 日活用户（%）")
    for date, weekday in zip(dates, daily["weekday"]):
        if weekday >= 5:
            for ax in axes:
                ax.axvspan(
                    date - pd.Timedelta(hours=12),
                    date + pd.Timedelta(hours=12),
                    color="#dbe7f0",
                    alpha=0.5,
                )
    axes[1].xaxis.set_major_locator(mdates.DayLocator(interval=4))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    save_figure(fig, directory, "daily_trends")
    users = tables["users"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), layout="constrained")
    bins = np.geomspace(max(1, users["events"].min()), users["events"].max(), 32)
    keys = users[[name + "_keys" for name in BEHAVIORS]].sum(axis=1)
    axes[0].hist(
        users["events"], bins=bins, color="#3777a8", alpha=0.6, label="原始次数"
    )
    axes[0].hist(
        keys,
        bins=bins,
        histtype="step",
        color="#d65f38",
        linewidth=2,
        label="四元组计数",
    )
    axes[0].set_xscale("log")
    axes[0].set_xlabel("31天每用户次数（对数坐标）")
    axes[0].set_ylabel("用户数")
    axes[0].legend()
    axes[0].set_title("用户活跃度：两种计数口径")
    activity = tables["activity_distribution"]
    axes[1].bar(activity["bin"], activity["users"], color="#b9cfdf")
    axes[1].set_ylabel("用户数")
    axes[1].tick_params(axis="x", rotation=30)
    right = axes[1].twinx()
    right.plot(
        activity["bin"], activity["purchase_rate"] * 100, color="#d65f38", marker="o"
    )
    right.set_ylabel("同期有购买记录用户占比（%）")
    right.set_ylim(0, 105)
    axes[1].set_title("全期活跃度与同期购买覆盖")
    save_figure(fig, directory, "user_activity")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), layout="constrained")
    purchases = tables["purchase_distribution"]
    axes[0].bar(purchases["bin"], purchases["users"], color="#d99477")
    axes[0].tick_params(axis="x", rotation=30)
    axes[0].set_xlabel("购买记录条数（不能解释为订单数）")
    axes[0].set_ylabel("用户数")
    axes[0].set_title("每用户购买记录分布")
    days = tables["purchase_day_distribution"]
    axes[1].bar(days["purchase_days"], days["users"], color="#8aafca")
    axes[1].set_xlabel("观测到购买记录的不同日期数")
    axes[1].set_ylabel("用户数")
    axes[1].set_title("跨日期购买分布（复购代理）")
    save_figure(fig, directory, "purchase_distributions")


def _funnel_and_transitions(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Contrast behavior coverage, a strict path and hour-level co-presence.

    Args:
        tables: Verified behavior supports and path summaries.
        directory: Figure output directory.
    """
    coverage = tables["behavior_sensitivity"].set_index("behavior").loc[list(BEHAVIORS)]
    strict = tables["strict_funnel"].iloc[0]
    values = [
        strict[key]
        for key in (
            "eligible_view_pairs",
            "cart_pairs",
            "favorite_pairs",
            "purchase_pairs",
        )
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    labels = [NAMES[name] for name in BEHAVIORS]
    axes[0].barh(labels[::-1], coverage["users"].to_numpy()[::-1], color="#83aac7")
    axes[0].set_title("各行为覆盖用户数（非顺序漏斗）")
    axes[0].set_xlabel("观测用户数")
    for index, value in enumerate(coverage["users"].to_numpy()[::-1]):
        axes[0].text(value, index, f" {value:,}", va="center")
    axes[0].set_xlim(0, 11500)
    axes[1].barh(labels[::-1], values[::-1], color="#d99477")
    axes[1].set_xscale("log")
    axes[1].set_xlabel("用户商品对数量（对数坐标）")
    axes[1].set_title("严格跨小时 pv→cart→fav→buy，7天随访")
    for index, value in enumerate(values[::-1]):
        axes[1].text(value, index, f" {value:,}", va="center")
    axes[1].set_xlim(10, max(values) * 5)
    save_figure(fig, directory, "coverage_and_strict_funnel")
    frame = tables["hour_transitions"]
    matrix = (
        frame.pivot(
            index="origin", columns="destination", values="probability"
        ).reindex(index=BEHAVIORS, columns=BEHAVIORS)
        * 100
    )
    fig, ax = plt.subplots(figsize=(8.5, 5.8), layout="constrained")
    image = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=100)
    ax.set_xticks(range(4), labels)
    ax.set_yticks(range(4), labels)
    for row in range(4):
        for column in range(4):
            ax.text(
                column,
                row,
                f"{matrix.iloc[row, column]:.1f}%",
                ha="center",
                va="center",
                color="#1b3043",
            )
    ax.set_xlabel("下一观测活跃小时出现的行为（间隔≤24小时）")
    ax.set_ylabel("当前活跃小时出现的行为")
    ax.set_title("相邻活跃小时行为共现关联（行和不要求100%）")
    fig.colorbar(image, ax=ax, label="条件出现比例（%）")
    save_figure(fig, directory, "hour_transitions")


def _future_associations(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Render prospective cohorts independently without pooling repeated users.

    Args:
        tables: Anchor-specific feature bins and binary future labels.
        directory: Figure output directory.
    """
    data = tables["forward_associations"]
    for anchor in tables["cohort_summary"]["anchor"]:
        selected = data.loc[data["anchor"] == anchor]
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
        for ax, feature in zip(axes, ("pv", "cart", "fav")):
            bins = selected.loc[selected["feature"] == feature]
            values = bins["purchase_rate"].to_numpy() * 100
            errors = np.vstack(
                [
                    values - bins["lower"].to_numpy() * 100,
                    bins["upper"].to_numpy() * 100 - values,
                ]
            )
            ax.errorbar(
                range(len(bins)),
                values,
                yerr=errors,
                color=COLORS[feature],
                marker="o",
                capsize=3,
                linewidth=2,
            )
            ax.set_xticks(range(len(bins)), bins["bin"], rotation=45, ha="right")
            ax.set_ylim(0, 105)
            ax.set_title("历史7天" + NAMES[feature] + "次数")
            ax.set_ylabel("未来7天有购买记录的用户占比（%）")
            for index, value, support in zip(range(len(bins)), values, bins["users"]):
                ax.annotate(
                    f"n={support}",
                    (index, value),
                    xytext=(0, 9),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8,
                )
        fig.suptitle(
            anchor + " 截点：历史行为与未来购买（描述性区间，非因果）",
            fontsize=16,
            fontweight="bold",
        )
        save_figure(fig, directory, "forward_associations_" + anchor.replace("-", ""))
    latest = tables["cohort_summary"]["anchor"].iloc[-1]
    fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
    for feature, label, color in (
        ("events", "原始记录次数", "#3777a8"),
        ("event_keys", "四元组计数", "#d65f38"),
    ):
        bins = data.loc[(data["anchor"] == latest) & (data["feature"] == feature)]
        ax.plot(
            bins["bin"],
            bins["purchase_rate"] * 100,
            marker="o",
            color=color,
            label=label,
        )
    ax.set_ylim(0, 105)
    ax.set_xlabel("历史7天次数分箱（两条线对应的人群可能不同）")
    ax.set_ylabel("未来7天购买用户占比（%）")
    ax.set_title("重复值口径敏感性：" + latest + " 截点")
    ax.legend()
    save_figure(fig, directory, "future_count_sensitivity")


def render_eda_charts(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Generate the user, time and path figures for dashboard one.

    Args:
        tables: All computed EDA frames.
        directory: Project-confined output directory.
    """
    configure_eda_plots()
    _heatmaps(tables, directory)
    _peak_day_sensitivity(tables, directory)
    _daily_and_distribution(tables, directory)
    _funnel_and_transitions(tables, directory)
    _future_associations(tables, directory)


def _peak_day_sensitivity(tables: dict[str, pd.DataFrame], directory: Path) -> None:
    """Compare purchase-hour patterns with and without the highest-purchase day.

    Args:
        tables: Full hourly summaries and daily purchase-record counts.
        directory: Figure output directory.

    Notes:
        This is a sensitivity view; no records are removed from source facts.
    """
    peak_day = tables["daily"].sort_values("buy").iloc[-1]["event_date"]
    hours = tables["hours"]
    full = hours.groupby(["weekday", "hour"])["buy"].mean().unstack()
    remaining = hours.loc[hours["event_date"] != peak_day]
    reduced = remaining.groupby(["weekday", "hour"])["buy"].mean().unstack()
    fig, axes = plt.subplots(1, 2, figsize=(15, 4.5), layout="constrained")
    labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    maximum = float(full.to_numpy().max())
    for ax, frame, title in zip(
        axes, (full, reduced), ("含全部日期", "敏感性视图：排除 " + peak_day)
    ):
        image = ax.imshow(frame, cmap="YlOrRd", vmin=0, vmax=maximum, aspect="auto")
        ax.set_xticks(range(0, 24, 3), [str(x) for x in range(0, 24, 3)])
        ax.set_yticks(range(7), labels)
        ax.set_xlabel("小时")
        ax.set_title(title)
    fig.colorbar(image, ax=axes, label="同星期小时的日均购买记录")
    fig.suptitle("峰值日是否主导星期规律？相同色阶对比", fontsize=16)
    save_figure(fig, directory, "peak_day_sensitivity")
