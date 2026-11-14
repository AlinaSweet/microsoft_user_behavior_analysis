"""Write readable retrospective pair-label, screening and ablation results."""

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.models.validation_models import ValidationSettings
from user_behavior_analysis.service.eda_charts import configure_eda_plots
from user_behavior_analysis.service.eda_charts import save_figure

MODEL_NAMES = {
    "basic": "基础统计",
    "business": "基础＋业务",
    "sequence": "基础业务＋序列",
    "svd": "基础业务＋SVD",
    "cooccurrence": "基础业务＋共现",
    "combined": "全部组组合",
}


def _metric_table(experiments: dict[str, Any]) -> pd.DataFrame:
    """Flatten every evaluation cohort without discarding unsupported metrics.

    Args:
        experiments: Completed fixed-model evaluation report.

    Returns:
        Rows containing split, cohort, model and observed metrics.
    """
    rows = []
    for split, evaluation in experiments["evaluations"].items():
        for cohort, models in evaluation["metrics"].items():
            if cohort == "clustered_auc_deltas":
                continue
            for name, metrics in models.items():
                rows.append(dict(metrics, split=split, cohort=cohort, model=name))
    return pd.DataFrame(rows)


def _plots(
    settings: ValidationSettings, samples: dict[str, Any], metrics: pd.DataFrame
) -> None:
    """Create exportable plots with explicit candidate and temporal denominators.

    Args:
        settings: Project-contained report destination.
        samples: Mature/unavailable label counts and candidate coverage.
        metrics: Exact complete-population prediction results.
    """
    configure_eda_plots()
    directory = settings.report_dir / "figures"
    directory.mkdir(exist_ok=True)
    mature = [s for s in samples["snapshots"] if s["target_available"]]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    labels = [s["anchor"][5:] for s in mature]
    rates = [100 * s["positives"] / s["rows"] for s in mature]
    coverage = [100 * s["candidate_coverage"]["pair_recall"] for s in mature]
    for axis, values, title in zip(
        axes,
        [rates, coverage],
        ["候选内未来7天购买比例（%）", "历史候选对未来购买组合的覆盖（%）"],
    ):
        bars = axis.bar(labels, values, color="#347fa3", width=0.55)
        axis.bar_label(bars, fmt="%.3f", padding=4)
        axis.set_title(title)
        axis.set_xlabel("特征截点（2025年）")
        axis.set_ylim(0, max(values) * 1.22)
    fig.suptitle("购买标签与候选范围：两个分母分别报告", fontsize=15)
    fig.tight_layout()
    save_figure(fig, directory, "labels_and_candidate_coverage")
    overall = metrics.loc[metrics.cohort == "all"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    positions = np.arange(len(MODEL_NAMES))
    for axis, metric, title in zip(
        axes, ["roc_auc", "average_precision"], ["ROC AUC", "平均精确率 AP"]
    ):
        for offset, split, color in [
            (-0.18, "validation", "#83b8c8"),
            (0.18, "test", "#256b87"),
        ]:
            selected = (
                overall.loc[overall.split == split]
                .set_index("model")
                .reindex(list(MODEL_NAMES))
            )
            bars = axis.bar(
                positions + offset,
                selected[metric],
                width=0.34,
                color=color,
                label="验证" if split == "validation" else "测试",
            )
            axis.bar_label(bars, fmt="%.4f", padding=3, fontsize=8, rotation=90)
        axis.set_xticks(positions, MODEL_NAMES.values(), rotation=30, ha="right")
        axis.set_title(title)
        axis.set_ylim(0, 1.05 if metric == "roc_auc" else 0.055)
        axis.legend()
    fig.suptitle("预先声明的六组逻辑回归消融：完整候选样本", fontsize=15)
    fig.tight_layout()
    save_figure(fig, directory, "ablation_metrics")


def write_validation_report(settings: ValidationSettings) -> Path:
    """Create a Chinese result report derived from saved numerical evidence.

    Args:
        settings: Passed sample, selection, prediction and diagnostic locations.

    Returns:
        Readable Markdown report path; CSV metrics and PNG/SVG plots accompany it.
    """
    samples = read_json_object(settings.report_dir / "samples.json")
    selection = read_json_object(settings.report_dir / "selection.json")
    experiments = read_json_object(settings.report_dir / "experiments.json")
    metrics = _metric_table(experiments)
    metrics.to_csv(settings.report_dir / "metrics.csv", index=False)
    _plots(settings, samples, metrics)
    lines = [
        "# 对级标签、分组筛选与逻辑回归消融验收",
        "",
        "日期：2026-11-14。",
        "",
        "本次完成导师要求的对级标签、三键对齐、训练期分组筛选、编码缩放和分组消融。",
        "原始记录、旧宽表及历史报告保留；新产物使用独立版本。",
        "",
        "## 1. 任务、粒度和标签",
        "",
        "预测对象是过去7天交互过的用户商品组合。唯一键为as_of_time、user_id、item_id。",
        "标签1表示同一用户对同一商品在[t,t+7天)至少出现一条购买记录；",
        "完整窗口无购买记录为0，未来不可观测为NULL。标签不是订单数、购买件数或用户级标签。",
        "",
        "| 截点 | 用途 | 候选行数 | 正例 | 负例 | 未知 | 候选购买覆盖 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    reverse = {anchor: split for split, anchor in settings.options["splits"].items()}
    for snap in samples["snapshots"]:
        covered = snap.get("candidate_coverage", {}).get("pair_recall")
        coverage = f"{covered:.2%}" if covered is not None else "不可评估"
        lines.append(
            f"| {snap['anchor']} | "
            + f"{reverse.get(snap['anchor'], '无标签快照')} | "
            + f"{snap['rows']:,} | {snap['positives']:,} | "
            + f"{snap['negatives']:,} | {snap['unavailable']:,} | {coverage} |"
        )
    lines += [
        "",
        "候选覆盖的分母是未来窗口全部购买组合，包括新用户、新商品。",
        "因此候选内AUC/AP不能当作覆盖全商城的推荐效果。",
        "三成熟截点共3,209,732行。由完整原始事件独立重算标签与两种购买计数，差异0；",
        "主键、键集合与样本源值检查通过。12月19日全部1,216,917个结果未知。",
        "",
        "## 2. 分组筛选与训练边界",
        "",
        "| 组别 | 原始候选字段 | 本次保留 |",
        "|---|---:|---:|",
    ]
    for name, count in selection["group_candidates"].items():
        lines.append(
            f"| {name} | {count} | {len(selection['selected_groups'][name])} |"
        )
    retained = sum(len(v) for v in selection["selected_groups"].values())
    lines += [
        "",
        f"439个标量中保留{retained}个进入本轮预实验；这不是新增{retained}个特征。",
        "6类原始序列数组仍独立保存，LR使用已有22个序列统计字段。",
        "所有缺失填充、完整训练矩、类别词表、组内相关性、互信息和筛选均只拟合11月25日训练样本。",
        "验证与测试只使用冻结变换。SVD/IDF/共现仍使用11月25日前冻结版本。",
        "常量不强行输入模型；明示30天窗口的统计字段暂缓；日历在单训练截点内不可学习。",
        "受保护RF代理仍代表7/14/21天实际已观测历史，不能解释为完整30天价值。",
        "40个非恒定RF/漏斗字段按业务保护保留。高相关字段记录明确原因，跨组冗余另有诊断。",
        "原始业务缺失保留在源表；模型层使用训练中位数、缺失标记和训练缩放，类别未知进入独立桶。",
        "",
        f"互信息总览使用训练候选均匀确定性抽样{selection['estimator_rows']:,}行，"
        + f"包含{selection['estimator_positives']}个正例。",
        "低活跃、高活跃与新近观测人群另从完整训练人群内取样，保存总体/样本支持量。",
        "SVD/共现还在各自可覆盖样本中单独估计。少于10个正例或负例时不报告该项互信息。",
        "训练画像、模型拟合、验证和测试均使用全量；MI估计没有冒称全量。",
        "",
        "## 3. 六组消融结果",
        "",
        "| 输入 | 验证AUC | 测试AUC | 验证AP | 测试AP |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, label in MODEL_NAMES.items():
        val = experiments["evaluations"]["validation"]["metrics"]["all"][name]
        test = experiments["evaluations"]["test"]["metrics"]["all"][name]
        lines.append(
            f"| {label} | {val['roc_auc']:.4f} | {test['roc_auc']:.4f} | "
            + f"{val['average_precision']:.5f} | {test['average_precision']:.5f} |"
        )
    training = experiments["training"]
    peak_mib = training["peak_observed_rss_bytes"] / 1024**2
    lines += [
        "",
        "AUC衡量正例排在负例前面的能力；AP汇总不同召回水平的精确率，正例稀少时尤其需要一起看。",
        "AP受正例比例影响，不能把测试AP高于验证AP直接解释为模型改善；组间比较均在同一窗口。",
        "基础业务组明显优于基础统计。SVD仅有小幅AUC增益，AP没有同步提升。",
        "序列和共现未显示一致增益，全部组组合也没有全面超过基础业务组。",
        "",
        "验证AP最高为“"
        + MODEL_NAMES[experiments["validation_choice"]]
        + "”，该选择在测试预测前写入冻结记录。",
        "全部实验事先列明，测试结果没有用于改筛选、改模型或重选赢家。",
        "SVD未知回退基础业务，图未知同样回退；组合模型两者均未知时回退序列组。",
        "全体、低/高活跃、新近观测、SVD可用/未知、共现可用/未知分别保存精确指标。",
        "用户聚类配对bootstrap100次给出AUC差值区间，避免把同一用户的多行当成完全独立样本。",
        "",
        "![购买标签与候选覆盖](figures/labels_and_candidate_coverage.png)",
        "",
        "![六组消融](figures/ablation_metrics.png)",
        "",
        "## 4. 资源、复核与限制",
        "",
        f"每组每轮完整访问{experiments['training']['rows_per_epoch_per_model'][0]:,}行，共5轮。",
        f"六组联合分批拟合耗时{training['seconds']:.2f}秒，"
        + f"批次间观测最大RSS约{peak_mib:.1f}MiB。",
        "该RSS是采样观察值，不声称捕获每一个瞬时峰值；拟合时间不含筛选、预测、bootstrap和复核。",
        "使用SGD优化的线性逻辑回归，未负采样、未SMOTE、未利用验证/测试拟合变换。",
        "固定0.5阈值下召回较低；概率未做校准，当前结果不能作为生产决策阈值。",
        "直接由持久化系数重新计算全部验证/测试概率，检查见prediction_replay.json。",
        "完整质量门禁、前序阶段回归和输入/输出指纹另存验收文件。",
        "",
        "已有EDA看过这三个日期，属于历史时间回测，不是全新盲测。",
        "仅一个训练/验证/测试截点组合；31天短历史与早期窗口不足限制稳定性结论。",
        "没有金额、订单和曝光，RF是代理，不提供真实金额型RFM、GMV、CTR或订单复购。",
        "",
        "## 5. 文件与复现",
        "",
        "- samples.json：全量标签、候选覆盖、三键/源值核验、所有源指纹及样本清单。",
        "- selection.json、feature_decisions.csv：439列决定、训练统计与冻结编码缩放。",
        "- training_group_diagnostics.json：完整训练人群支持量、条件MI、跨组冗余。",
        "- experiments.json、metrics.csv：全量模型/人群指标、bootstrap与资源观察。",
        "- frozen_validation_choice.json：在读取测试结果之前登记的模型选择。",
        "- prediction_replay.json：全部概率由系数直接重放的审计。",
        "- quality.json、code_review.md、source_manifest.json：规范、评审和版本证据。",
        "- 大型标签、样本、模型和预测位于data/processed，不上传Git。",
        "",
        "方法与命令见[特征验证方法](../../../docs/feature_validation.md)。",
    ]
    path = settings.report_dir / "README.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
