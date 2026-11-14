"""Export current EDA and training-group feature evidence as standalone figures."""

from pathlib import Path
from typing import Any

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.models.encoding_models import CompletionSettings
from user_behavior_analysis.service.eda_charts import configure_eda_plots
from user_behavior_analysis.service.eda_charts import save_figure
from user_behavior_analysis.service.wide_contracts import identifier


def render_current_eda(directory: Path, data: dict[str, Any]) -> None:
    """Export ten core visual analyses using the full default filtered payload.

    Args:
        directory: Current figure destination.
        data: Independently reconciled default full-window aggregate response.
    """
    configure_eda_plots()
    directory.mkdir(parents=True, exist_ok=True)
    _render_eda_1(directory, data)
    _render_eda_2(directory, data)
    _render_eda_3(directory, data)
    _render_eda_4(directory, data)


def _render_eda_1(directory: Path, data: dict[str, Any]) -> None:
    """Render a coherent subset of independently reconciled EDA charts.

    Args:
        directory: Figure destination directory.
        data: Full default-window, source-verified aggregate payload.
    """
    behaviors = pd.DataFrame(data["behaviors"]).set_index("behavior_type")
    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(
        ["浏览", "收藏", "加购", "购买"],
        behaviors.reindex([1, 2, 3, 4]).records,
        color=["#42829f", "#8a6ba2", "#bb963e", "#cd7c42"],
    )
    axis.set_ylabel("原始日志记录数")
    axis.set_title("全部有效记录的四行为分布")
    fig.tight_layout()
    save_figure(fig, directory, "eda_behavior")
    daily = pd.DataFrame(data["daily"])
    fig, axis = plt.subplots(figsize=(11, 4.5))
    for kind, name in [(1, "浏览"), (2, "收藏"), (3, "加购"), (4, "购买")]:
        part = daily.loc[daily.behavior_type == kind]
        axis.plot(pd.to_datetime(part.day), part.records, label=name)
    axis.set_title("每日行为记录趋势")
    axis.set_ylabel("日志记录数")
    axis.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    save_figure(fig, directory, "eda_daily")
    heat = np.zeros((7, 24))
    for row in data["heatmap"]:
        heat[row["weekday"], row["hour"]] += (
            row["records"] / data["weekday_days"][str(row["weekday"])]
        )
    fig, axis = plt.subplots(figsize=(11, 4))
    image = axis.imshow(heat, aspect="auto", cmap="YlOrBr")
    axis.set_yticks(range(7), ["周一", "周二", "周三", "周四", "周五", "周六", "周日"])
    axis.set_xlabel("小时")
    axis.set_title("按星期出现天数校正的日均记录量")
    fig.colorbar(image, ax=axis, label="日均日志记录")
    fig.tight_layout()
    save_figure(fig, directory, "eda_hour_heatmap")


def _render_eda_2(directory: Path, data: dict[str, Any]) -> None:
    """Render a coherent subset of independently reconciled EDA charts.

    Args:
        directory: Figure destination directory.
        data: Full default-window, source-verified aggregate payload.
    """
    fig, axis = plt.subplots(figsize=(8, 4.5))
    activity = pd.DataFrame(data["activity_exact"])
    axis.scatter(activity.records, activity.users, s=7, alpha=0.5)
    axis.set_xscale("log")
    axis.set_xlabel("每用户日志记录数（对数）")
    axis.set_ylabel("用户数")
    axis.set_title("用户活跃记录长尾")
    fig.tight_layout()
    save_figure(fig, directory, "eda_activity")
    purchases = pd.DataFrame(data["purchase_distribution"])
    purchases["bin"] = pd.cut(
        purchases.buy_records,
        [-1, 0, 1, 4, 9, np.inf],
        labels=["0", "1", "2–4", "5–9", "10+"],
    )
    counts = purchases.groupby("bin", observed=False).users.sum()
    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(counts.index.astype(str), counts.to_numpy(dtype=float), color="#cb8548")
    axis.set_title("用户购买记录分布（不代表订单数）")
    axis.set_ylabel("用户数")
    fig.tight_layout()
    save_figure(fig, directory, "eda_purchase_distribution")


def _render_eda_3(directory: Path, data: dict[str, Any]) -> None:
    """Render a coherent subset of independently reconciled EDA charts.

    Args:
        directory: Figure destination directory.
        data: Full default-window, source-verified aggregate payload.
    """
    categories = pd.DataFrame(data["categories"])
    fig, axis = plt.subplots(figsize=(9, 6))
    part = categories.head(20).iloc[::-1]
    axis.barh(part.category_id, part.records, color="#42829f")
    axis.set_title("类目交互记录量Top20")
    axis.set_xlabel("日志记录数")
    fig.tight_layout()
    save_figure(fig, directory, "eda_categories")
    ordered = categories.sort_values("pv_records", ascending=False)
    fig, axis = plt.subplots(figsize=(8, 4.5))
    for column, name in [("pv_records", "浏览记录"), ("buy_records", "购买记录")]:
        axis.plot(
            np.arange(1, len(ordered) + 1),
            ordered[column].cumsum() / ordered[column].sum(),
            label=name,
        )
    axis.set_xlabel("按浏览量排序的类目累计个数")
    axis.set_ylabel("累计记录占比")
    axis.set_title("类目长尾贡献")
    axis.legend()
    fig.tight_layout()
    save_figure(fig, directory, "eda_category_tail")
    quadrants = pd.DataFrame(data["item_quadrants"])
    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.scatter(quadrants.pv_records, quadrants.purchase_coverage, alpha=0.3, s=10)
    axis.set_xscale("log")
    axis.set_xlabel("浏览记录量（对数）")
    axis.set_ylabel("同窗浏览组合购买覆盖")
    axis.axvline(
        data["quadrant_thresholds"]["pv_records"], color="#aaa", linestyle="--"
    )
    axis.axhline(
        data["quadrant_thresholds"]["purchase_coverage"], color="#aaa", linestyle="--"
    )
    axis.set_title("有至少20个浏览组合的商品；展示至多1500个")
    fig.tight_layout()
    save_figure(fig, directory, "eda_item_quadrants")


def _render_eda_4(directory: Path, data: dict[str, Any]) -> None:
    """Render a coherent subset of independently reconciled EDA charts.

    Args:
        directory: Figure destination directory.
        data: Full default-window, source-verified aggregate payload.
    """
    fig, axis = plt.subplots(figsize=(9, 4.5))
    axis.barh(
        ["成熟浏览", "跨小时加购", "再跨小时收藏", "再跨小时购买"][::-1],
        data["funnel"]["stage_counts"][::-1],
        color="#ca8246",
    )
    axis.set_title("完整7天随访的指定严格路径")
    axis.set_xlabel("用户商品组合数")
    fig.tight_layout()
    save_figure(fig, directory, "eda_mature_funnel")
    values = np.full((4, 4), np.nan)
    for row in data["transitions"]:
        values[row["current"] - 1, row["following"] - 1] = row["rate"]
    fig, axis = plt.subplots(figsize=(7, 5))
    image = axis.imshow(values, cmap="YlOrBr", vmin=0, vmax=1)
    axis.set_xticks(range(4), ["浏览", "收藏", "加购", "购买"])
    axis.set_yticks(range(4), ["浏览", "收藏", "加购", "购买"])
    for left in range(4):
        for right in range(4):
            axis.text(
                right, left, f"{values[left, right]:.1%}", ha="center", va="center"
            )
    axis.set_title("下个观测活跃小时多标签转移；行和可超过100%")
    fig.colorbar(image, ax=axis)
    fig.tight_layout()
    save_figure(fig, directory, "eda_hour_transitions")


def render_feature_evidence(
    settings: CompletionSettings, selection: dict[str, Any], samples: dict[str, Any]
) -> None:
    """Export full selected numeric correlations and separate group MI rankings.

    Args:
        settings: Current report and fixed training sample settings.
        selection: Accepted prior training-only decisions and MI estimates.
        samples: Accepted exact-pair sample manifest.
    """
    configure_eda_plots()
    directory = settings.report_dir / "figures"
    numeric = [
        r
        for r in selection["decisions"]
        if r["status"] == "selected" and r["dtype"] != "category"
    ]
    train = next(
        s for s in samples["snapshots"] if s["anchor"] == selection["fit_anchor"]
    )
    with duckdb.connect() as connection:
        connection.execute("SET memory_limit='768MB'")
        connection.execute("SET threads=1")
        connection.read_parquet(
            [str(PROJECT_ROOT / p["path"]) for p in train["sample_parts"]]
        ).create_view("training")
        names = list(
            dict.fromkeys(
                [r["name"] for r in numeric]
                + ["pair_svd_available", "pair_cooc_graph_known"]
            )
        )
        columns = ",".join(identifier(name) for name in names)
        frame = connection.execute(
            "SELECT "
            + columns
            + (" FROM training ORDER BY hash(user_id,item_id," + "?) LIMIT 100000"),
            [settings.options["seed"]],
        ).df()
    correlations = frame[[r["name"] for r in numeric]].corr(method="spearman")
    correlations.to_csv(settings.report_dir / "selected_correlations.csv")
    rows = pd.DataFrame(selection["decisions"])
    rows.sort_values(
        ["group", "training_mi"], ascending=[True, False], na_position="last"
    ).to_csv(settings.report_dir / "importance_rank.csv", index=False)
    for group in ("basic", "business", "sequence", "svd", "cooccurrence"):
        ranked = rows.loc[(rows.group == group) & rows.training_mi.notna()].sort_values(
            "training_mi", ascending=False
        )
        part = ranked.head(15).iloc[::-1]
        fig, axis = plt.subplots(figsize=(11, 6))
        axis.barh(part.name, part.training_mi, color="#417f9c")
        axis.set_xlabel("训练样本互信息估计（nat）")
        axis.set_title(group + " 组内互信息前15；不跨组直接排高级特征")
        axis.tick_params(axis="y", labelsize=8)
        fig.tight_layout()
        save_figure(fig, directory, "mi_" + group)
        _render_group_correlation(directory, frame, ranked, group)


def _render_group_correlation(
    directory: Path, frame: pd.DataFrame, ranked: pd.DataFrame, group: str
) -> None:
    """Separate advanced-group correlations by actual training feature coverage.

    Args:
        directory: Current figure and group-matrix destination.
        frame: Deterministic training-only numeric sample including coverage flags.
        ranked: Ordered within-group information estimates.
        group: One predeclared feature family.
    """
    names = [name for name in ranked.name if name in frame.columns]
    flag = {"svd": "pair_svd_available", "cooccurrence": "pair_cooc_graph_known"}
    part = frame.loc[frame[flag[group]] == 1, names] if group in flag else frame[names]
    part = part.loc[:, part.nunique(dropna=True) > 1]
    correlations = part.corr(method="spearman")
    correlations.to_csv(directory / ("correlation_" + group + ".csv"))
    names = list(part.columns)[:12]
    if not names:
        return
    fig, axis = plt.subplots(figsize=(11, 9))
    image = axis.imshow(
        correlations.loc[names, names], cmap="coolwarm", vmin=-1, vmax=1
    )
    axis.set_xticks(range(len(names)), names, rotation=90, fontsize=7)
    axis.set_yticks(range(len(names)), names, fontsize=7)
    axis.set_title(group + f" 组内Spearman；覆盖内训练样本n={len(part):,}，最多12列")
    fig.colorbar(image, ax=axis, shrink=0.7)
    fig.tight_layout()
    save_figure(fig, directory, "correlation_" + group)
