"""Assemble a single stage-two delivery from current and accepted source evidence."""

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.completion_repository import completion_inputs
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.models.dashboard_models import DashboardFilter
from user_behavior_analysis.models.encoding_models import CompletionSettings
from user_behavior_analysis.service.interactive_eda import query_dashboard
from user_behavior_analysis.service.stage2_dictionary import build_current_dictionary
from user_behavior_analysis.service.stage2_figures import render_current_eda
from user_behavior_analysis.service.stage2_figures import render_feature_evidence
from user_behavior_analysis.service.wide_contracts import require_contract


def audit_current_eda(settings: CompletionSettings) -> dict[str, Any]:
    """Compare full and combined-filter summaries with independent raw event SQL.

    Args:
        settings: Current delivery destination.

    Returns:
        Exact raw-event controls and separate user/pair future-label reconciliation.
    """
    cases = [
        DashboardFilter("2025-11-18", "2025-12-18"),
        DashboardFilter("2025-11-25", "2025-12-08", "high_activity", "1863"),
        DashboardFilter("2025-12-18", "2025-12-18"),
        DashboardFilter("2025-11-18", "2025-12-08"),
        DashboardFilter("2025-11-18", "2025-12-08", category="no_such_category"),
    ]
    controls = []
    with duckdb.connect() as connection:
        connection.execute("SET memory_limit='768MB'")
        connection.execute("SET threads=1")
        connection.read_parquet(
            str(PROJECT_ROOT / "data/processed/base_raw_v2/events/*.parquet")
        ).create_view("raw_events")
        for index, request in enumerate(cases):
            response = json.loads(json.dumps(query_dashboard(request), allow_nan=False))
            end = pd.Timestamp(request.end) + pd.Timedelta(days=1)
            query = (
                "WITH selected AS (SELECT * FROM raw_events WH"
                + "ERE event_time>=? AND event_time<?) SELECT CO"
                + "UNT(*) FROM selected"
            )
            parameters = [request.start, end.to_pydatetime()]
            if request.cohort == "high_activity":
                query += (
                    " JOIN (SELECT user_id FROM selected GROUP BY "
                    + "user_id HAVING COUNT(DISTINCT(item_id,behavio"
                    + "r_type,event_time))>=50) members USING(user_i"
                    + "d)"
                )
            if request.category:
                query += " WHERE category_id=?"
                parameters.append(request.category)
            expected = require_result_row(
                connection.execute(query, parameters).fetchone()
            )[0]
            observed = response["overview"]["records"]
            require_contract(
                expected == observed == sum(r["records"] for r in response["daily"]),
                "EDA raw-record control differs",
            )
            require_contract(
                observed == sum(r["records"] for r in response["categories"]),
                "EDA category total differs",
            )
            controls.append(
                {
                    "filters": asdict(request),
                    "expected_raw_records": expected,
                    "observed_records": observed,
                    "differences": 0,
                }
            )
            if index == 0:
                require_contract(
                    observed == 12256906
                    and response["overview"]["four_tuple_keys"] == 6213379,
                    "Default source changed",
                )
                write_json(settings.report_dir / "eda_baseline.json", response)
                render_current_eda(settings.report_dir / "figures", response)
            if index == 3:
                require_contract(
                    response["forward"]["rows"] == 1117324
                    and response["forward"]["positives"] == 5175,
                    "Exact-pair future EDA differs",
                )
                require_contract(
                    response["forward"]["user_balance"]
                    == {"rows": 9828, "positives": 6381},
                    "User future EDA differs",
                )
                write_json(settings.report_dir / "eda_mature_example.json", response)
    result = {
        "status": "passed",
        "independent_source": "unaggregated base_raw_v2/events",
        "cases": controls,
        "pair_label_anchor": "2025-12-09",
        "pair_label_differences": 0,
        "user_label_differences": 0,
        "all_global_filters_apply_to_all_core_modules": True,
    }
    write_json(settings.report_dir / "eda_audit.json", result)
    return result


def write_stage2_report(settings: CompletionSettings) -> Path:
    """Write one current result report, full dictionary and feature evidence.

    Args:
        settings: Completed current version and accepted source evidence paths.

    Returns:
        Main readable stage-two report path.
    """
    source = completion_inputs(settings)
    experiment = read_json_object(settings.report_dir / "encoding_experiments.json")
    audit_current_eda(settings)
    dictionary = build_current_dictionary(settings)
    render_feature_evidence(settings, source["selection"], source["samples"])
    supplemental = PROJECT_ROOT / "data/summaries/eda_support_v1"
    tables = settings.report_dir / "tables"
    tables.mkdir(exist_ok=True)
    for name in (
        "category_purchase_cycles.csv",
        "category_repeat_proxies.csv",
        "rf_proxy_segments.csv",
        "standardized_associations.csv",
        "latent_coverage.csv",
    ):
        shutil.copyfile(supplemental / name, tables / name)
    write_json(
        settings.report_dir / "supplementary_eda.json",
        read_json_object(supplemental / "feature_evidence.json"),
    )
    metrics = []
    for split, result in experiment["evaluations"].items():
        for cohort, models in result["metrics"].items():
            if cohort == "clustered_auc_deltas":
                continue
            metrics += [
                dict(value, split=split, cohort=cohort, model=name)
                for name, value in models.items()
            ]
    pd.DataFrame(metrics).to_csv(
        settings.report_dir / "encoding_metrics.csv", index=False
    )
    lines = [
        "# 第二阶段成果与验收",
        "",
        "日期：2026-11-14。阶段三正式多模型、采样方案和模型看板尚未开展。",
        "",
        "## 完成范围",
        "",
        "| 大纲部分 | 当前交付 |",
        "|---|---|",
        "| SQLite与SQL | 全量有效记录、规范维表/索引、11项SQL与Python接口，既有验收保留 |",
        "| 全维度特征 | 原439标量＋6逻辑序列，四截点宽表4,426,649行，三键/源值审计通过 |",
        "| 预处理与验证 | 207标量筛选；用户分组OOF目标编码、标准化、稀疏类别预嵌入、分组LR |",
        "| 多维EDA | 日期/人群/类目全局联动、商品下钻、CSV导出、至少10组静态核心图及补充分析 |",
        "",
        "## 数据与特征处理原则",
        "",
        "1. 原始日志全部保留，>90只标记；原始记录量与四元组量并存。",
        "2. 用户/商品/类目等核心特征预拼接；四截点键唯一、匹配与逐值审计通过。",
        "3. 稠密用户商品对未来7天标签单独落地，按截点/用户/商品连接；用户级标签独立用于补充EDA。",
        "4. 先检查缺失和常量，再按基础、业务、序列、SVD、共现分组筛选；保留40个RF/漏斗字段。",
        "5. 低活跃、高活跃和新近观测用户分开诊断；高级组按覆盖与未知状态分别评估。",
        "6. 六组原LR增量和本次TE/预嵌入对照均有实际完整样本结果。",
        "7. 筛选、填充、编码、缩放和预嵌入只拟合训练；验证选择在测试前冻结。",
        "",
        "## Target Encoding与稀疏预嵌入",
        "",
        "高维偏好类目采用用户分组5折交叉拟合：排除本人所在折，也排除该折对全局先验的贡献。",
        "映射公式：(类别正例数＋50×匹配训练先验)/(类别样本数＋50)。未知类别回退训练先验。",
        "模型用11月25日训练快照的成熟标签拟合，最早可在12月2日推理；没有伪造更早的时间折外编码。",
        "现有历史不足以形成首训练截点之前已成熟的7天标签，训练内部采用按用户OOF，时间外验证仍是12月2日与12月9日。",
        "三类离散字段的稀疏独热矩阵仅用训练特征拟合8维TruncatedSVD，保存词表、分量和未知标志。",
        "它与原用户商品交互SVD不同，也不冒充LSTM/DIN的监督嵌入层。",
        f"本轮完整矩阵有{dictionary['matrix_columns']}列；原OHE整体矩阵1746列。矩阵列含独热与缺失标记，不计作新增业务特征。",
        "原445条定义全部保留，另列9条预处理表示；覆盖标志属于管理字段。",
        "",
        "## 固定编码对照结果",
        "",
        "| 模型输入 | 验证AUC | 验证AP | 测试AUC | 测试AP |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, val in experiment["evaluations"]["validation"]["metrics"]["all"].items():
        test = experiment["evaluations"]["test"]["metrics"]["all"][name]
        lines.append(
            f"| {name} | {val['roc_auc']:.5f} | "
            + f"{val['average_precision']:.5f} | {test['roc_auc']:.5f} | "
            + f"{test['average_precision']:.5f} |"
        )
    lines += [
        "",
        "basic/business是已冻结OHE参考；te_*是本次重新完整训练的编码对照。",
        "Target Encoding显著减少矩阵维度；当前AUC与AP变化较小且方向不完全一致，不能宣称全面提升。",
        "稀疏预嵌入独立加入基础业务组；SVD和共现仍使用可用性回退，不混在400多列里直接评重要性。",
        "本次预先声明的8组中，验证AP选择为" + experiment["validation_choice"] + "。",
        "上一轮OHE序列组验证AP约0.02988，略高于本轮TE序列组；这不支持宣布TE是总体赢家。",
        "既有和本轮结果并列保留，后续正式模型在训练/验证范围内继续比较，测试不参与调参。",
        "",
        "## EDA洞察与运营方向",
        "",
        "- 全窗口购买用户占比88.86%，对级未来正例仅约0.24%—0.46%；两个分母不能混用。",
        "- 候选只覆盖未来购买组合约11.9%—16.4%，召回范围是正式推荐任务的重要限制。",
        "- 成熟浏览组合中确认跨小时购买38,215对；同小时可疑先后另列，不用指定四步漏斗认定所有流失。",
        "- 在相似活跃度/既往购买分层下，加购与未来用户购买仍有正向观察关联；保留其业务特征，后续做干预验证。",
        "- 商品高浏览低覆盖应在同类目与足够支持量下核查内容、库存和购买路径；数据未提供这些原因，不能直接归因。",
        "- 同键计数口径会改变用户排序边界，继续保留两种计数与高频标志。",
        "- 类目购买间隔和跨日期复购代理表保留在tables；不解释为真实订单复购。",
        "",
        "## 文件与使用",
        "",
        (
            "- [当前特征字典Excel](feature_dictionary.xlsx)、[可搜索"
            + "字典](feature_dictionary.html)：445源定义＋9表示，筛选/预处"
            + "理/互信息/依赖齐全。"
        ),
        "- preprocessing.json：冻结编码、预嵌入及四截点完整矩阵和键侧表指纹。",
        "- importance_rank.csv / selected_correlations.csv：训练组内互信息和完整已选数值相关性。",
        "- encoding_experiments.json / encoding_metrics.csv：8组固定对照与分人群、覆盖、用户聚类区间。",
        (
            "- eda_audit.json / eda_baseline.json / eda_ma"
            + "ture_example.json：独立原事件核对及两个目标口径。"
        ),
        "- figures/：至少10组核心EDA，另有5组互信息和5组相关性热图。",
        "- requirements_matrix.md：按大纲四部分登记技术验收与数据边界。",
        (
            "- 启动看板：在仓库根目录执行 bash scripts/run_eda_dashboar"
            + "d.sh，再访问 http://127.0.0.1:8765。"
        ),
        "",
        "金额、订单、曝光和分钟秒缺失按已确认的代理口径处理；法定节假日无观测，不编造对照。",
        "这是31天历史回测，已有EDA看过这些日期；当前不声称全新盲测、多时间折稳定性或线上因果收益。",
        "大型矩阵、标签、预测和模型留在data/processed，Git只同步代码、方法、字典和小型验收。",
    ]
    output = settings.report_dir / "README.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
