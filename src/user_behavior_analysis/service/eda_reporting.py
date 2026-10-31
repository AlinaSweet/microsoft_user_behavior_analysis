"""Publish a self-contained dashboard and readable tables from saved EDA results."""

import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.models.eda_models import EDASettings
from user_behavior_analysis.service.eda_charts import render_eda_charts
from user_behavior_analysis.service.eda_entity_charts import render_entity_charts


def _figure(directory: Path, stem: str, caption: str) -> str:
    """Embed a verified figure with explanatory text in standalone HTML.

    Args:
        directory: Figure output directory.
        stem: Registered figure filename stem.
        caption: Metric interpretation and exploration guidance.

    Returns:
        Escaped HTML containing a complete embedded PNG.
    """
    data = base64.b64encode((directory / (stem + ".png")).read_bytes()).decode()
    return (
        '<figure><img alt="'
        + html.escape(caption, quote=True)
        + '" src="data:image/png;base64,'
        + data
        + '"><figcaption>'
        + html.escape(caption)
        + "</figcaption></figure>"
    )


def _switch_group(
    directory: Path, options: list[tuple[str, str]], caption: str, default: int = 0
) -> str:
    """Create one local chart switch with an explicit effect boundary.

    Args:
        directory: Figure output location.
        options: Figure stems paired with visible option labels.
        caption: Shared chart interpretation.
        default: Initially selected option.

    Returns:
        A standalone selector affecting only its own chart group.
    """
    choices = []
    panels = []
    for index, (stem, label) in enumerate(options):
        selected = " selected" if index == default else ""
        hidden = " hidden" if index != default else ""
        choices.append(
            '<option value="'
            + str(index)
            + '"'
            + selected
            + ">"
            + html.escape(label)
            + "</option>"
        )
        panels.append(
            '<div data-panel="'
            + str(index)
            + '"'
            + hidden
            + ">"
            + _figure(directory, stem, caption)
            + "</div>"
        )
    return (
        '<div class="switchgroup"><label>只切换本图：<select data-switch>'
        + "".join(choices)
        + "</select></label>"
        + "".join(panels)
        + "</div>"
    )


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    """Serialize selected analytical columns as a readable Markdown table.

    Args:
        frame: Complete aggregate table.
        columns: Ordered columns to publish.

    Returns:
        Header, separator and data rows with safe cell formatting.
    """
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame[columns].itertuples(index=False, name=None):
        values = []
        for value in row:
            text = f"{value:.6g}" if isinstance(value, float) else str(value)
            values.append(text.replace("|", "/").replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _write_tables(directory: Path, tables: dict[str, pd.DataFrame]) -> None:
    """Publish all small analysis tables while keeping user profiles local.

    Args:
        directory: Report output directory.
        tables: Loaded analytical tables.
    """
    selected = [
        "count_controls",
        "behavior_sensitivity",
        "daily",
        "activity_distribution",
        "purchase_distribution",
        "purchase_day_distribution",
        "cohort_summary",
        "top_categories_volume",
        "top_categories_coverage",
        "top_items_volume",
        "top_items_coverage",
        "strict_funnel",
        "branch_funnels",
        "hour_transitions",
        "transition_boundary",
        "preference_top5",
        "activity_thresholds",
        "quadrant_thresholds",
        "flagged_cohort_comparison",
    ]
    lines = [
        "# 看板一 EDA 对应统计表",
        "",
        "输入为全部有效原记录。rate/share/probability字段使用0–1比例；",
        "lower/upper为描述性Wilson区间。用户ID级明细保留在本地。",
        "",
    ]
    for name in selected:
        frame = tables[name]
        lines.extend(
            ["## " + name, "", _markdown_table(frame, list(frame.columns)), ""]
        )
    for anchor in tables["cohort_summary"]["anchor"]:
        frame = tables["forward_associations"]
        frame = frame.loc[frame["anchor"] == anchor]
        lines.extend(
            [
                "## 过去7天 → 未来7天：" + anchor,
                "",
                _markdown_table(frame, list(frame.columns)),
                "",
            ]
        )
    (directory / "tables.md").write_text("\n".join(lines), encoding="utf-8")


def _write_dashboard(
    directory: Path, metrics: dict[str, Any], tables: dict[str, pd.DataFrame]
) -> None:
    """Assemble four EDA modules and learning prompts into an offline HTML report.

    Args:
        directory: Report directory containing exported figures.
        metrics: Core dataset measures.
        tables: Analytical tables used for cohort and path explanations.
    """
    figures = directory / "figures"
    cards = [
        ("有效行为记录", f"{metrics['records']:,}"),
        ("用户", f"{metrics['users']:,}"),
        ("商品", f"{metrics['items']:,}"),
        ("类目", f"{metrics['categories']:,}"),
        ("观测自然日", str(metrics["calendar_days"])),
        ("31天购买用户占比", f"{metrics['purchase_user_share']:.2%}"),
    ]
    sections = [
        '<section id="overview"><h2>01 / 数据概览与统计口径</h2><div class="cards">',
        "".join(
            '<div class="card"><span>'
            + label
            + "</span><strong>"
            + value
            + "</strong></div>"
            for label, value in cards
        ),
        '</div><div class="note"><b>先问统计对象，再问比例。</b>购买记录占全部行为的'
        + f" {metrics['purchase_record_share']:.2%}，"
        + "不等于用户购买率，更不等于未来用户商品样本的正例比例。"
        + "平均每个活跃用户日有 "
        + f"{metrics['observed_hour_buckets_per_active_user_day']:.2f}"
        + " 个小时桶有记录；这不是在线时长。</div>",
        _figure(
            figures,
            "forward_cohort_balance",
            "用户级样本：只纳入历史7天有活动的用户；标签为未来7天是否观测到任意购买。"
            + "每个截点单独统计；当前正例占比约57%–67%，不能预设为极端类别不平衡。",
        ),
        '</section><section id="users"><h2>02 / 用户行为时序与分布</h2>',
        _switch_group(
            figures,
            [
                ("heatmap_events", "全部行为"),
                ("heatmap_pv", "浏览"),
                ("heatmap_cart", "加购"),
                ("heatmap_fav", "收藏"),
                ("heatmap_buy", "购买"),
            ],
            "每个星期在31天中出现的次数不同，因此用日均记录量比较。"
            + "探索：浏览高峰与购买高峰是否一致？单个日期是否主导了均值？",
        ),
        _figure(
            figures,
            "heatmap_purchase_share",
            "同小时购买用户数 / 同小时活跃用户数。同小时内先后无法判断；"
            + "这是时段内购买覆盖，而不是浏览后购买的顺序转化。",
        ),
        _figure(
            figures,
            "daily_trends",
            "阴影为周六周日，不代表完整法定工作日历。探索：购买抬升是访问人数增加，"
            + "还是活跃用户中的购买比例提高？不能直接将波动归因于促销。",
        ),
        _figure(
            figures,
            "peak_day_sensitivity",
            "峰值日会影响星期平均值；排除只是敏感性展示，原始记录仍全部保留。"
            + "请比较两幅图，再判断星期规律是否稳定。",
        ),
        _figure(
            figures,
            "user_activity",
            "左图比较原始次数与四元组计数；右图是同期关联。"
            + "探索：活跃用户购买更多是否只是因为观察机会更多？未来窗口图帮助进一步判断。",
        ),
        _figure(
            figures,
            "purchase_distributions",
            "购买记录次数与跨日期再次购买分别展示。两条购买记录不一定是两个订单，"
            + "不同日期再次购买也是当前字段条件下的复购代理。",
        ),
        '</section><section id="items"><h2>03 / 商品、类目与长尾</h2>',
    ]
    for kind, label in (("category", "类目"), ("item", "商品")):
        sections.extend(
            [
                "<h3>" + label + "双维度排名</h3>",
                _switch_group(
                    figures,
                    [
                        (kind + "_ranking_volume", "按交互记录量"),
                        (kind + "_ranking_coverage", "按购买覆盖率下界"),
                    ],
                    "覆盖率 = 同窗既浏览又购买的用户商品对 / 浏览用户商品对。"
                    + "它不保证先浏览后购买。按覆盖率排名设置最小样本数，并按Wilson下界排序，"
                    + "降低小样本高比例的影响；区间没有校正用户聚类与多重筛选。",
                ),
            ]
        )
    sections.extend(
        [
            _figure(
                figures,
                "category_long_tail",
                "类目按浏览量排序。前20%类目贡献 "
                + f"{metrics['top_20pct_categories_pv_share']:.2%}"
                + " 浏览记录。探索：高流量类目与高购买贡献类目是否一致？",
            ),
            _figure(
                figures,
                "item_quadrants",
                "没有曝光字段，横轴使用浏览记录量。只展示至少20个浏览用户商品对的商品；"
                + "纵轴加入20个全局先验伪观察作描述性平滑。四象限阈值是探索性设置，"
                + "不是已经确定的商品运营策略。",
            ),
            '</section><section id="links"><h2>04 / 转化路径与特征关联</h2>',
            _figure(
                figures,
                "coverage_and_strict_funnel",
                "左图的四种行为覆盖没有先后顺序。右图只验证指定的跨小时四步路径，"
                + "使用有完整7天随访的用户商品对；不把收藏视为所有购买的必经步骤。",
            ),
            _figure(
                figures,
                "alternative_purchase_paths",
                "各路径分母相同，但路径可以重叠。允许同小时的结果是候选路径，"
                + "无法确认小时内顺序；严格跨小时路径会漏掉真实的小时内转化。",
            ),
            _figure(
                figures,
                "hour_transitions",
                "同一小时可以有多种行为，行和可以大于100%。这里只比较间隔不超过24小时的"
                + "相邻观测活跃小时；不能解释为点击级下一步概率，也不能推断退出。",
            ),
            _switch_group(
                figures,
                [
                    ("forward_associations_" + value.replace("-", ""), value + " 截点")
                    for value in tables["cohort_summary"]["anchor"]
                ],
                "横轴仅使用截点前7天行为；纵轴为未来7天购买用户比例。"
                + "每个点显示样本数和描述性区间。探索：加购和收藏的关联是否比浏览更稳定？"
                + "这一结论还要在相似活跃度人群内对照。",
                default=2,
            ),
            _figure(
                figures,
                "activity_category_preferences",
                "用层内四元组计数占比比较兴趣结构，避免高活跃组仅因总量大而看起来偏好更强。"
                + "每层自己的Top5类目在tables.md；类目ID没有真实商品名称语义。",
            ),
            _figure(
                figures,
                "duplicate_sensitivity",
                "四元组计数用于敏感性比较，全部有效原记录仍保留。"
                + "计数减少本身不能证明原始记录错误。",
            ),
            _figure(
                figures,
                "future_count_sensitivity",
                "相同分箱下，原始次数与四元组次数对应的人群可能不同。"
                + "下一步可比较用户排名稳定性、同活跃层差异和未来窗口关联，"
                + "而不是仅凭总记录量下降选择去重规则。",
            ),
            "</section><section><h2>建议一起继续研究的五个问题</h2><ol>",
            "<li><b>重复值：</b>原始次数、四元组计数、不同活跃小时，哪一种描述"
            + "对未来购买更稳定？高频用户是否集中在特定类目或时段？</li>",
            "<li><b>购买意向：</b>在相似活跃度下，加购/收藏较多的人是否仍更容易"
            + "在未来购买？避免把总体活跃度误当成行为本身的作用。</li>",
            "<li><b>商品机会：</b>高浏览低覆盖商品是否只是类目基准不同？"
            + "先在同类目、相似样本量内比较，再讨论运营动作。</li>",
            "<li><b>时间稳定性：</b>同一关联在不同截点和不同日期是否一致？"
            + "31天窗口不足以推断长期季节规律。</li>",
            "<li><b>类目偏好：</b>活跃度分层的偏好差异能否在排除整体热门度后保留？"
            + "可进一步构建偏好集中度、跨类目探索度。</li></ol></section>",
        ]
    )
    style = (
        "body{font:16px/1.7 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;"
        + "margin:0;background:#f2f5f7;color:#193247}header,main{max-width:1200px;"
        + "margin:auto;padding:28px}header{padding-top:46px}h1{font-size:36px;"
        + "line-height:1.3;margin-bottom:10px}h2{font-size:25px;margin-top:0}"
        + "section{background:white;border:1px solid #dce4ea;border-radius:14px;"
        + "padding:26px;margin:22px 0;scroll-margin-top:80px}nav{position:sticky;top:0;"
        + "z-index:3;background:#193247;color:white;padding:14px;text-align:center}"
        + "nav a{color:white;text-decoration:none;margin:0 18px}.cards{display:grid;"
        + "grid-template-columns:repeat(3,1fr);gap:12px}.card{padding:16px;"
        + "background:#f0f5f8;border-radius:9px}.card span{display:block;color:#587083}"
        + ".card strong{font-size:28px}.note{background:#fff3e6;padding:16px;"
        + "border-left:4px solid #d58a46;margin:20px 0}figure{margin:24px 0}"
        + "img{display:block;width:100%;height:auto}figcaption{color:#526b7d;"
        + "padding:10px 14px;background:#f4f7fa;border-radius:6px}"
        + "select{font:inherit;padding:8px;border:1px solid #b9cbd8;border-radius:6px}"
        + "[hidden]{display:none!important}a{color:#266a9d}li{margin:10px 0}"
        + "@media(max-width:700px){header,main{padding:14px}section{padding:14px}"
        + "h1{font-size:27px}.cards{grid-template-columns:repeat(2,1fr)}"
        + "nav a{margin:0 6px;font-size:13px}}"
    )
    script = (
        "document.querySelectorAll('[data-switch]').forEach(s=>"
        + "s.addEventListener('change',()=>s.closest('.switchgroup')"
        + ".querySelectorAll('[data-panel]').forEach(p=>"
        + "p.hidden=p.dataset.panel!==s.value)));"
    )
    document = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        + '<meta name="viewport" content="width=device-width,initial-scale=1">'
        + "<title>看板一 · 用户行为 EDA</title><style>"
        + style
        + "</style>"
        + "<header><p>微软商城用户行为分析 / EDA / 2026-10-29</p>"
        + "<h1>从行为分布，走向可检验的特征想法</h1>"
        + "<p>观测窗口：2025-11-18 至 2025-12-18。全量有效记录保留，"
        + "超过90条/用户小时只标记。本版为固定全量窗口的EDA报告，"
        + "图组切换仅影响对应图表；尚未提供全局日期、人群、类目联动筛选。</p>"
        + "<p>阅读顺序：看数据 → 找差异 → 排除口径影响 → 提出下一步验证。</p>"
        + "</header><nav><a href='#overview'>数据概览</a>"
        + "<a href='#users'>用户与时间</a><a href='#items'>商品与类目</a>"
        + "<a href='#links'>路径与关联</a></nav><main>"
        + "".join(sections)
        + "</main><script>"
        + script
        + "</script></html>"
    )
    (directory / "dashboard.html").write_text(document, encoding="utf-8")


def render_saved_eda(settings: EDASettings) -> None:
    """Render saved statistical results without rerunning full database queries.

    Args:
        settings: Validated EDA configuration and report/cache paths.
    """
    directory = settings["report_dir"]
    payload = json.loads((directory / "analysis.json").read_text())
    tables = {name: pd.DataFrame(rows) for name, rows in payload["tables"].items()}
    for name in ("users", "latest_cohort", "item_quadrants"):
        tables[name] = pd.read_parquet(settings["cache_dir"] / (name + ".parquet"))
    render_eda_charts(tables, directory / "figures")
    render_entity_charts(tables, directory / "figures")
    _write_tables(directory, tables)
    _write_dashboard(directory, payload["metrics"], tables)
    manifest = {
        "source_database_sha256": payload["metadata"]["source_sha256"],
        "png_figures": len(list((directory / "figures").glob("*.png"))),
        "svg_figures": len(list((directory / "figures").glob("*.svg"))),
        "files": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
            for path in sorted(directory.rglob("*"))
            if path.is_file() and path.name != "artifact_manifest.json"
        ],
    }
    (directory / "artifact_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
