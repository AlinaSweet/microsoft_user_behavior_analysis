"""Publish feature definitions, actual counts, lineage and data quality."""

import html
import json
from collections import Counter
from typing import Any

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.feature_explanations import explain_feature
from user_behavior_analysis.service.feature_explanations import feature_window_label

OWNER_NAMES = {
    "user": "用户",
    "item": "商品",
    "category": "类目",
    "pair": "用户商品对",
    "user_category": "用户类目",
    "time": "时间",
    "sequence": "序列输入",
}


def _humanize(text: str) -> str:
    """Translate mechanical registry labels without changing field names or formulas.

    Args:
        text: Registered Chinese description containing a few source labels.

    Returns:
        Reader-friendly business wording.
    """
    for old, new in (
        ("不同items数量", "不同商品数量"),
        ("不同users数量", "不同用户数量"),
        ("不同categories数量", "不同类目数量"),
        ("pv原始", "浏览原始"),
        ("cart原始", "加购原始"),
        ("fav原始", "收藏原始"),
        ("buy原始", "购买原始"),
        ("pv不同", "浏览不同"),
        ("cart不同", "加购不同"),
        ("fav不同", "收藏不同"),
        ("buy不同", "购买不同"),
    ):
        text = text.replace(old, new)
    return text


def _dictionary_markdown(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    """Render every produced field with its real formula and output location.

    Args:
        rows: Unique persisted-field definitions.
        summary: Count conventions and snapshot coverage.

    Returns:
        Complete Markdown dictionary using the supplied five-column structure.
    """
    lines = [
        "# 全维度特征字典",
        "",
        "构建开始于2026-10-29，完成日期以本轮执行记录为准。全量保留有效原记录。",
        "本字典沿用参考表的“所在表、特征名、特征、计算方法、特征描述”五列。",
        "计数："
        + str(summary["scalar_features"])
        + "个标量字段、"
        + str(summary["sequence_fields"])
        + "类逻辑序列输入。"
        + "SVD的32个坐标已包含在标量数中；不另重复相加。",
        "",
        "ID、as_of_time、覆盖管理字段、标签、分片和重复截点不计为新增特征。",
        "所有特征严格读取截点前；30天不足时记录实际覆盖，12月19日未来标签不可用。",
        "",
    ]
    for owner, owner_name in OWNER_NAMES.items():
        lines.extend(
            [
                "## " + owner_name,
                "",
                "| 所在表 | 特征名 | 特征 | 计算方法 | 特征描述与产物 |",
                "|---|---|---|---|---|",
            ]
        )
        for row in rows:
            if row["table"] != owner:
                continue
            cells = [
                owner_name,
                row["name"],
                row["chinese_name"],
                row.get("calculation_explanation", row["calculation"]),
                row["description"]
                + "；窗口="
                + feature_window_label(row["window_days"])
                + "；存储="
                + row.get("storage_dtype", row["dtype"])
                + "；缺失="
                + row["missing_policy"]
                + "；data/processed/features_raw_v2/"
                + row["artifact"],
            ]
            lines.append(
                "| "
                + " | ".join(
                    str(value).replace("|", "\\|").replace("\n", " ") for value in cells
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _dictionary_html(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    """Create a fully offline searchable feature reference for a novice reader.

    Args:
        rows: Produced field definitions with final schema types.
        summary: Actual scalar and sequence counts.

    Returns:
        Standalone HTML with searchable definitions, formulas and lineage.
    """
    content = []
    for row in rows:
        content.append(
            '<article data-owner="'
            + row["table"]
            + '"><h3>'
            + html.escape(row["name"])
            + '</h3><p class="meaning">'
            + html.escape(row["chinese_name"])
            + "</p><p>"
            + html.escape(row["description"])
            + "</p><dl><dt>所在表 / 特征族</dt><dd>"
            + OWNER_NAMES[row["table"]]
            + " / "
            + html.escape(row["family"])
            + "</dd><dt>窗口与类型</dt><dd>"
            + feature_window_label(row["window_days"])
            + " / "
            + html.escape(row.get("storage_dtype", row["dtype"]))
            + "</dd><dt>缺失如何解释</dt><dd>"
            + html.escape(row["missing_policy"])
            + "</dd><dt>产物位置</dt><dd>data/processed/features_raw_v2/"
            + html.escape(row["artifact"])
            + "</dd></dl><details>"
            + "<summary>查看计算方法</summary><pre>"
            + html.escape(row.get("calculation_explanation", row["calculation"]))
            + "</pre></details></article>"
        )
    controls = (
        '<input id="search" placeholder="搜索特征名、含义、计算方法">'
        + '<select id="owner"><option value="">全部表</option>'
        + "".join(
            '<option value="' + key + '">' + value + "</option>"
            for key, value in OWNER_NAMES.items()
        )
        + "</select><span id='count'></span>"
    )
    style = (
        "body{font:16px/1.65 -apple-system,'PingFang SC',sans-serif;background:#f2f5f7;"
        + (
            "color:#20394b;margin:0}header,main{max-w"
            + "idth:1100px;margin:auto;padding:24px}"
        )
        + "header{padding-top:40px}h1{font-size:30px}article{background:white;"
        + "border:1px solid #d7e1e8;border-radius:12px;padding:22px;margin:18px 0}"
        + (
            "h3{font-size:18px;word-break:break-all}."
            + "meaning{color:#b15e37;font-weight:600}"
        )
        + "dl{display:grid;grid-template-columns:160px 1fr;gap:8px}"
        + "dd{margin:0;overflow-wrap:anywhere}dt{color:#607789}"
        + (
            "input,select{font:inherit;padding:10px;b"
            + "order:1px solid #b8cbd8;border-radius:6p"
            + "x}"
        )
        + "input{width:min(520px,65%)}pre{white-space:pre-wrap;overflow-wrap:anywhere;"
        + (
            "background:#eef3f7;padding:14px}.tools{p"
            + "osition:sticky;top:0;background:#f2f5f7;"
        )
        + "padding:14px 0}summary{cursor:pointer}[hidden]{display:none!important}"
        + (
            "@media(max-width:600px){header,main{padd"
            + "ing:14px}dl{grid-template-columns:1fr}}"
        )
    )
    script = (
        "const q=document.querySelector('#search'),o=document.querySelector('#owner');"
        + "function filter(){let n=0;document.querySelectorAll('article').forEach(a=>{"
        + "a.hidden=!!((o.value&&a.dataset.owner!==o.value)||"
        + "!a.innerText.toLowerCase().includes(q.value.toLowerCase()));"
        + (
            "if(!a.hidden)n++;});document.querySelect"
            + "or('#count').textContent='显示 '+n+' 项';}"
        )
        + (
            "q.addEventListener('input',filter);o.add"
            + "EventListener('change',filter);filter();"
        )
    )
    return (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        + '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + "<title>全维度特征字典</title><style>"
        + style
        + "</style><header>"
        + "<h1>已经构建了哪些特征？</h1><p>"
        + str(summary["scalar_features"])
        + " 个标量字段，"
        + str(summary["sequence_fields"])
        + " 类序列输入。"
        + "管理字段和标签不计入特征数量。每项均有实际产物。</p>"
        + "<p>历史窗口为[t-W天,t)，未来标签单独存放。"
        + "RF为无金额条件下的代理分群；小时内顺序未知。</p></header><main>"
        + '<div class="tools">'
        + controls
        + "</div>"
        + "".join(content)
        + "</main><script>"
        + script
        + "</script></html>"
    )


def create_feature_delivery(settings: FeatureSettings) -> dict[str, Any]:
    """Publish only actually completed snapshots and their complete field dictionary.

    Args:
        settings: Feature-system directories and required anchors.

    Returns:
        Unique field counts, per-snapshot dimensions and full delivery lineage.

    Raises:
        ValueError: A snapshot is incomplete, inconsistent or missing registered fields.
    """
    snapshots = []
    for anchor in settings.options["anchors"]:
        path = settings.output_dir / "snapshots" / anchor / "completion.json"
        report: dict[str, Any] = json.loads(path.read_text())
        if report["status"] != "completed":
            raise ValueError("Incomplete snapshot: " + anchor)
        snapshots.append(report)
    definitions = snapshots[0]["definitions"]
    names = {row["name"] for row in definitions}
    for snapshot in snapshots:
        if {row["name"] for row in snapshot["definitions"]} != names:
            raise ValueError("Snapshot feature dictionaries disagree")
        if any(
            not row["counts_match"] for row in snapshot["controls"]["entity_controls"]
        ):
            raise ValueError("Snapshot count control failed")
    for row in definitions:
        row["description"] = _humanize(row["description"])
        row["chinese_name"] = _humanize(row["chinese_name"])
    for row in definitions:
        row["calculation_explanation"] = explain_feature(
            row["name"], row["calculation"]
        )
    scalar = [row for row in definitions if row["table"] != "sequence"]
    sequence = [row for row in definitions if row["table"] == "sequence"]
    counts = Counter(row["table"] for row in definitions)
    families = Counter(row["family"] for row in definitions)
    summary = {
        "scalar_features": len(scalar),
        "sequence_fields": len(sequence),
        "dictionary_rows": len(definitions),
        "by_table": dict(counts),
        "by_family": dict(families),
        "svd_coordinate_columns": 2 * settings.options["svd_components"],
        "svd_fit_anchor": settings.options["fit_anchor"],
        "snapshot_rows": [
            {
                "anchor": row["anchor"],
                "users": row["entities"]["user"]["rows"],
                "items": row["entities"]["item"]["rows"],
                "categories": row["entities"]["category"]["rows"],
                "candidate_pairs": row["model_inputs"]["rows"],
                "scalar_columns": row["scalar_feature_count"],
                "history_coverage_30d": row["history"]["coverage"]["30"],
                "future_label_available": row["user_targets"]["label_available"],
                "positives": row["user_targets"]["positives"],
                "negatives": row["user_targets"]["negatives"],
            }
            for row in snapshots
        ],
        "candidate_snapshot_rows": sum(
            row["model_inputs"]["rows"] for row in snapshots
        ),
        "candidate_scope": "user-item pairs observed during the preceding seven days",
        "not_counted": [
            "IDs",
            "as_of_time",
            "coverage management",
            "targets",
            "parts",
            "repeat cutoffs",
        ],
        "future_labels_are_features": False,
        "supervised_purchase_model_trained": False,
    }
    latest = {row["name"]: row for row in snapshots[-1]["quality"]}
    for row in definitions:
        row["latest_quality"] = latest.get(row["name"])
    dictionary = {"summary": summary, "features": definitions}
    write_json(settings.report_dir / "feature_dictionary.json", dictionary)
    write_json(
        settings.report_dir / "quality_profiles.json",
        {
            "distinct_counts": (
                "approximate; min/max constant checks are" + " exact for numeric fields"
            ),
            "profiles": [row for snap in snapshots for row in snap["quality"]],
        },
    )
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "docs/feature_dictionary.md").write_text(
        _dictionary_markdown(definitions, summary), encoding="utf-8"
    )
    (settings.report_dir / "feature_dictionary.html").write_text(
        _dictionary_html(definitions, summary), encoding="utf-8"
    )
    base = json.loads((PROJECT_ROOT / "data/catalog/base_raw_v2.json").read_text())
    catalog = {
        "dataset": "features_raw_v2",
        "status": "completed",
        "summary": summary,
        "source_catalog": "data/catalog/base_raw_v2.json",
        "source_catalog_sha256": sha256_file(
            PROJECT_ROOT / "data/catalog/base_raw_v2.json"
        ),
        "source_database_sha256": sha256_file(settings.source_database),
        "policy": "preserve_all_valid_records_flag90",
        "base_tables": base["tables"],
        "latent_files": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted((settings.output_dir / "latent").glob("*"))
            if path.is_file()
        ],
        "snapshots": [
            {"anchor": row["anchor"], "files": row["files"]} for row in snapshots
        ],
        "dictionary": "outputs/reports/feature_system_20261029/feature_dictionary.json",
        "storage": "large Parquet, NPZ and analytical caches stay local",
    }
    write_json(PROJECT_ROOT / "data/catalog/features_raw_v2.json", catalog)
    write_json(settings.report_dir / "summary.json", summary)
    write_json(
        PROJECT_ROOT / "data/catalog/current_datasets.json",
        {
            "counting_policy": "preserve_all_valid_records_flag90",
            "standard_events": "data/processed/base_raw_v2/events",
            "base_catalog": "data/catalog/base_raw_v2.json",
            "analysis_database": "data/processed/analysis_raw_v1/behavior.sqlite",
            "feature_catalog": "data/catalog/features_raw_v2.json",
            "feature_root": "data/processed/features_raw_v2",
            "legacy_references": [
                "data/interim/clean_v1/events",
                "data/processed/base_v1",
            ],
            "validated_source": "data/interim/clean_v1/validated",
        },
    )
    return summary
