"""Publish deeper EDA tables and an offline explanation of feature evidence."""

import json
from html import escape
from typing import Any

import pandas as pd

from user_behavior_analysis.models.feature_models import FeatureSettings

FIGURES = (
    (
        "activity_controlled_intent",
        "控制活跃度后的意向比较",
        "在相似历史记录量和既往购买状态下比较，减少活跃度混杂；仍是观察关联。",
    ),
    (
        "standardized_intent_contrasts",
        "标准化后的购买比例差异",
        "各分层中每组至少30人，再按该截点人群权重汇总；覆盖不足单独标注。",
    ),
    (
        "duplicate_rank_sensitivity",
        "原记录与四元组口径敏感性",
        "用户排名总体接近，但前10%人群仍有8.6%不同，不能据此删除同小时记录。",
    ),
    (
        "rf_proxy_segments",
        "RF与活跃代理群体",
        "用观测购买日期、最近购买与最近活跃分组；不是金额RFM或客户真实价值。",
    ),
    (
        "latent_feature_coverage",
        "冻结SVD与共现规则覆盖",
        "模型只在最早截点前拟合；后续新商品为未知，不能把缺失向量当作已学会。",
    ),
    (
        "candidate_feature_correlations",
        "候选特征相关性",
        "用于发现计数列冗余；只展示12个用户字段的初步相关性，尚未正式筛选。",
    ),
    (
        "category_purchase_delays",
        "类目跨小时转化间隔",
        "首次浏览留足7天随访；同小时先后未知，只统计可确认跨小时购买的组合。",
    ),
    (
        "category_repeat_proxies",
        "类目跨日期复购代理",
        "同用户商品在首购日期后1至7个自然日再次出现购买记录，不代表订单复购。",
    ),
)


def _table_html(rows: list[dict[str, Any]]) -> str:
    """Render a small audit table with safe text and explicit missing values.

    Args:
        rows: Already aggregated public report records.

    Returns:
        HTML table with escaped headers and values.
    """
    if not rows:
        return "<p>暂无可观测结果。</p>"
    keys = list(rows[0])
    header = "".join("<th>" + escape(key) + "</th>" for key in keys)
    body = []
    for row in rows:
        cells = []
        for key in keys:
            value = row[key]
            if isinstance(value, float):
                value = f"{value:.4f}"
            cells.append(
                "<td>" + escape(str(value) if value is not None else "不可用") + "</td>"
            )
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<table><thead><tr>"
        + header
        + "</tr></thead><tbody>"
        + "".join(body)
        + ("</tbody></table>")
    )


def publish_feature_eda(settings: FeatureSettings) -> None:
    """Export EDA aggregation tables and their fully offline gallery.

    Args:
        settings: Completed feature EDA and report destinations.
    """
    directory = settings.eda_report_dir
    analysis = json.loads((directory / "analysis.json").read_text(encoding="utf-8"))
    evidence = json.loads(
        (directory / "feature_evidence.json").read_text(encoding="utf-8")
    )
    tables = {
        "activity_strata": analysis["conditional_associations"],
        "standardized_associations": analysis["standardized_associations"],
        "rf_proxy_segments": evidence["feature_evidence"]["segments"],
        "latent_coverage": evidence["feature_evidence"]["latent_coverage"],
        "category_purchase_cycles": evidence["category_evidence"]["cycles"],
        "category_repeat_proxies": evidence["category_evidence"]["repeat_proxies"],
    }
    for name, rows in tables.items():
        pd.DataFrame(rows).to_csv(
            directory / (name + ".csv"), index=False, encoding="utf-8-sig"
        )
    cards = []
    for name, title, explanation in FIGURES:
        cards.append(
            '<section class="card" data-search="'
            + escape(title + explanation)
            + '"><h2>'
            + title
            + "</h2><p>"
            + explanation
            + '</p><a href="figures/'
            + name
            + '.svg" target="_blank">'
            + '<img src="figures/'
            + name
            + '.png" alt="'
            + title
            + '" loading="lazy"></a></section>'
        )
    table = _table_html(tables["standardized_associations"])
    document = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        + '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + "<title>EDA补充与特征证据</title><style>"
        + "body{margin:0;background:#f3f5f7;color:#193047;font:16px/1.7 "
        + (
            '"PingFang SC",Arial,sans-serif}main{max'
            + "-width:1180px;margin:auto;padding:32px}"
        )
        + "a{color:#166c9b}h1{font-size:34px}h2{font-size:23px}"
        + ".card,.intro{background:white;border-radius:14px;padding:24px;margin:22px 0}"
        + ".card img{width:100%;height:auto}.note{border-left:4px solid #cf8451;"
        + "padding-left:15px}input{padding:12px;font-size:16px;width:min(90%,640px);"
        + "border:1px solid #aebac4;border-radius:8px}table{border-collapse:collapse;"
        + "font-size:13px}th,td{border-bottom:1px solid #dce3e8;padding:9px;"
        + "text-align:left;white-space:nowrap}.scroll{overflow:auto}"
        + "button{background:#193e58;color:white;border:0;padding:12px;"
        + "border-radius:8px;cursor:pointer}@media print{input,button{display:none}}"
        + "</style><main><p>微软商城用户行为分析 · 2026-10-30</p>"
        + '<h1>从EDA发现问题，再构建特征</h1><div class="intro">'
        + "<p>基线26幅图之外，新增8幅深入分析图。数据保留全部有效原记录，"
        + "每用户小时超过90条只标记。下方搜索只筛选图组，不改变统计样本。</p>"
        + '<p><a href="../eda_dashboard1_20261029/dashboard.html">看板一基线</a> · '
        + '<a href="../feature_system_20261029/feature_dictionary.html">445项特征字典</a>'
        + ' · <a href="../feature_system_20261029/feature_dictionary.xlsx">下载Excel</a>'
        + ' · <a href="README.md">口径与分析说明</a></p>'
        + '<p class="note">有加购用户的未来购买比例在分层标准化后仍高出6.38、9.47、'
        + "8.77个百分点；不能解释为加购导致购买。原记录/四元组用户前10%重合91.4%。"
        + "SVD在最新候选对中可用约23.02%，需要后续消融验证。</p>"
        + '<label for="search">按主题查找图表</label><br><input id="search" '
        + 'placeholder="例如：类目、复购、覆盖、活跃度"><button id="reset">清空</button>'
        + '<p id="count">显示8组图表</p></div>'
        + "".join(cards)
        + '<section class="card"><h2>分层标准化明细</h2><p>difference_percentage_points'
        + "为百分点；population_coverage是纳入充分支持分层的人群比例。</p>"
        + '<div class="scroll">'
        + table
        + "</div>"
        + '<p><a href="standardized_associations.csv">下载全部明细</a></p></section>'
        + '<section class="card"><h2>下一步探索</h2><ol>'
        + "<li>保留/不使用同键次数特征时，未来标签关联是否稳定？</li>"
        + "<li>加购信号在冷商品、不同类目和不同历史窗口是否一致？</li>"
        + "<li>首选类目集中与广泛探索用户，购买路径有何差异？</li>"
        + "<li>补充训练历史或滚动拟合后，SVD覆盖与效果能否改善？"
        + "必须在各训练折内部拟合。</li></ol>"
        + "<p>观测期无中国大陆法定节假日，无法比较节假日效应。"
        + "相关性、分群与序列均受31天、小时精度、无金额/订单/曝光限制。</p>"
        + "</section></main><script>"
        + 'const search=document.getElementById("search");'
        + 'function filter(){let n=0;document.querySelectorAll("[data-search]")'
        + ".forEach(card=>{const show=card.datase"
        + "t.search.includes(search.value.trim());"
        + (
            "card.hidden=!show;if(show)n++});docume"
            + 'nt.getElementById("count").textContent='
        )
        + '"显示"+n+"组图表"}search.addEventListener("input",filter);'
        + 'document.getElementById("reset").addEventListener("click",()=>{'
        + 'search.value="";filter()});</script></html>'
    )
    (directory / "dashboard.html").write_text(document, encoding="utf-8")
