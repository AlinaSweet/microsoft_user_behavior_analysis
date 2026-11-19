"""Join original definitions, exact training decisions and new representations."""

import html
from dataclasses import asdict
from pathlib import Path
from typing import Any

import joblib  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.completion_repository import completion_inputs
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.encoding_models import CompletionSettings


def build_current_dictionary(settings: CompletionSettings) -> dict[str, Any]:
    """Keep all 445 original definitions and explicitly label nine derived outputs.

    Args:
        settings: Current complete feature delivery paths.

    Returns:
        Source definitions, current preprocessing decisions and representation lineage.
    """
    sources = completion_inputs(settings)
    wide = read_json_object(settings.validation.wide_catalog)
    audit = read_json_object(verify_registered_file(wide["audit_report"]))
    source = read_json_object(verify_registered_file(audit["source_catalog"]))
    original = read_json_object(Path(source["dictionary"]))
    prepared = read_json_object(settings.report_dir / "preprocessing.json")
    state = joblib.load(verify_registered_file(prepared["transform_file"]))
    decisions = {r["name"]: r for r in sources["selection"]["decisions"]}
    features = []
    for row in original["features"]:
        decision = decisions.get(row["name"], {})
        method = "独立序列数组，小时并列与PAD/UNK掩码保留"
        if row["table"] != "sequence":
            if row["name"] == state.target.column:
                method = "训练用户5折OOF Target Encoding；推理冻结训练映射；可用时间为12月2日"
            elif row["dtype"] == "category":
                method = "低维类别：训练词表独热，未知桶独立；另有稀疏预嵌入对照"
            elif row["name"] in state.numeric.medians:
                method = "训练中位数填充；训练均值/标准差缩放；按需保留缺失指示"
            else:
                method = "本轮暂缓或排除，保留原始源字段"
        features.append(
            dict(
                row,
                record_type="source",
                current_group=decision.get("group", "sequence_array"),
                current_preprocessing=method,
                current_status=decision.get("status", "separate_sequence_input"),
                decision_reason=decision.get(
                    "reason", "raw arrays are not LR scalar columns"
                ),
                training_mi=decision.get("training_mi"),
                training_missing_rate=decision.get("missing_rate"),
                business_protected=decision.get("protected", False),
            )
        )
    representations = [
        {
            "name": state.target.column + "__te",
            "record_type": "representation",
            "family": "目标编码",
            "table": "model_matrix",
            "dtype": "float32",
            "chinese_name": "用户偏好类目的交叉拟合购买率编码",
            "calculation": "(非本用户折正例数+50×非本用户折先验)/(非本用户折样本数+50)，再用训练OOF均值标准化",
            "current_preprocessing": "训练用户分组OOF；验证测试冻结全训练映射；未知类目回退训练先验",
            "current_status": "produced",
            "decision_reason": "原大纲高维类别Target Encoding交付",
            "current_group": "business",
            "training_mi": None,
            "business_protected": False,
            "description": "不是原始购买率，不读取验证/测试标签；模型拟合不早于训练标签成熟时间",
        }
    ]
    for index in range(settings.options["embedding_dimensions"]):
        representations.append(
            {
                "name": f"category_embedding_{index:02d}",
                "record_type": "representation",
                "family": "类别稀疏预嵌入",
                "table": "model_matrix",
                "dtype": "float32",
                "chinese_name": f"三类离散特征的稀疏预嵌入第{index + 1}维",
                "calculation": "训练词表稀疏one-hot × 冻结TruncatedSVD分量，再用训练投影均值/标准差缩放",
                "current_preprocessing": "仅训练特征拟合，不使用标签；未知类别桶及覆盖标志独立保留",
                "current_status": "produced",
                "decision_reason": "独立高级特征组增量对照",
                "current_group": "embedding",
                "training_mi": None,
                "business_protected": False,
                "description": "输入为偏好类目、RF代理群、生命周期状态；与原用户商品交互SVD不同",
            }
        )
    result = {
        "source_entries": 445,
        "source_scalars": 439,
        "source_sequences": 6,
        "selected_source_scalars": 207,
        "derived_representation_entries": len(representations),
        "matrix_columns": prepared["encoded_matrix_columns"],
        "features": features,
        "representations": representations,
        "matrix_column_names": prepared["column_names"],
        "coverage_management": ["embedding_all_known"],
        "fit_contract": {
            "anchor": prepared["fit_anchor"],
            "target_encoder_available_at": state.target.available_at,
            "training_only": True,
            "numeric": asdict(state.numeric),
        },
    }
    write_json(settings.report_dir / "feature_dictionary.json", result)
    rows = []
    for row in features + representations:
        rows.append(
            "<tr>"
            + "".join(
                "<td>" + html.escape(str(row.get(key, "不可用"))) + "</td>"
                for key in [
                    "name",
                    "chinese_name",
                    "family",
                    "current_group",
                    "current_preprocessing",
                    "current_status",
                    "decision_reason",
                    "training_mi",
                ]
            )
            + "</tr>"
        )
    document = (
        '<!doctype html><html lang="zh-CN"><meta chars'
        + 'et="utf-8"><title>当前特征字典</title><style>body{f'
        + "ont:14px/1.6 system-ui;margin:28px;color:#243"
        + "b4a}input{padding:10px;width:480px;max-width:"
        + "90%}table{border-collapse:collapse;margin-top"
        + ":20px}td,th{border-bottom:1px solid #dbe4ea;p"
        + "adding:8px;text-align:left;vertical-align:top"
        + "}th{position:sticky;top:0;background:#eaf0f4}"
        + "tr[hidden]{display:none}td:first-child{font-f"
        + "amily:monospace}p{max-width:1100px}</style><h"
        + "1>当前特征字典</h1><p>445条原始定义（439标量＋6序列）；另列9条预处理表示"
        + "。207个原始标量进入预实验，最终编码矩阵259列。覆盖管理字段不计入特征数量。缺失互信息"
        + '表示未估计，不代表零。</p><input id="search" placeholder'
        + '="按字段、业务含义、处理方法或保留原因搜索"><table><thead><tr>'
    )
    document += "".join(
        "<th>" + key + "</th>"
        for key in [
            "字段",
            "中文含义",
            "特征族",
            "实验组",
            "当前预处理",
            "状态",
            "原因",
            "训练互信息",
        ]
    )
    document += (
        "</tr></thead><tbody>"
        + "".join(rows)
        + (
            "</tbody></table><script>document.querySelecto"
            + "r('#search').addEventListener('input',e=>docu"
            + "ment.querySelectorAll('tbody tr').forEach(r=>"
            + "r.hidden=!r.textContent.toLowerCase().include"
            + "s(e.target.value.toLowerCase())));</script></"
            + "html>"
        )
    )
    (settings.report_dir / "feature_dictionary.html").write_text(
        document, encoding="utf-8"
    )
    return result
