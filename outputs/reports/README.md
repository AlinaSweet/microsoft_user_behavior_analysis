# 阶段成果与验收索引

本目录按项目大纲的阶段和任务阅读；同一任务的生成结果、原始测量和独立验收分别保留。
全部Git文件的逐项说明见[按阶段逐文件导航](../../docs/files_by_stage.md)。

## 第一阶段：数据工程体系搭建与理论储备

| 部分 | 成果入口 | 文件作用 |
|---|---|---|
| 1.1 工程环境与版本管理 | [环境](environment_check.json)、[工程基准](engineering_benchmark.md)、[规范](coding_standard_compliance.json)、[数据未变检查](coding_standard_data_validation.json)、[Git政策](git_artifact_check.json) | 依赖/资源、真实测量、代码与同步范围检查 |
| 1.2 文献与技术方案 | [研究成果](stage1_step2_research.md)、[研究验收](stage1_step2_audit.md)、[结构化验收](stage1_step2_audit.json) | 论文、工具比较和方案完整性 |
| 1.3 加载、清洗与质量 | [清洗成果](stage1_step3/README.md)、[客户小时分布与保留政策依据](duplicate_review_20261024/README.md) | 原始记录校验、异常诊断、四元组频数和独立核对 |
| 1.4 压缩、Parquet与中间表 | [预处理测量与验收](stage1_step4/README.md) | 事件类型、格式读写和三维聚合；历史归并测量与当前全记录版本分开 |

## 第二阶段：深度特征工程与多维度探索性分析

| 部分 | 成果入口 | 文件作用 |
|---|---|---|
| 2.1 SQLite与SQL | [数据库与11项SQL](stage2_step1_20261024/README.md) | 建库、完整导出清单与可同步摘要 |
| 2.2 全维度特征 | [源特征生成](feature_system_20261029/README.md)、[预拼接验收](prejoined_wide_20261107/README.md)、[正式字典](stage2/feature_dictionary.xlsx) | 439标量、6逻辑序列、四截点宽表与逐值审计 |
| 2.3 预处理与有效性 | [分组筛选和第一轮LR](feature_validation_20261114/README.md)、[编码对照及冻结矩阵](stage2/README.md) | 对级标签、训练期筛选、259列矩阵、指标及完整重放 |
| 2.4 多维EDA | [在线看板](https://alinasweet.github.io/microsoft_user_behavior_analysis/)、[发布视图清单](dashboard_publication_20261117/manifest.json)、[核心静态图](stage2/figures/)、[补充统计表](stage2/tables/)、[EDA验收](stage2/eda_audit.json) | 行为、时间、漏斗、分群、商品和类目探索 |

## 阶段综合验收

| 入口 | 范围 |
|---|---|
| [第一阶段验收](stage1/audit.json) | 四个任务的整体回归及其环境、质量、清洗与预处理证据 |
| [第一二阶段成果与验收报告](stage1_stage2_review_20261114_01/completion_report.md) | 8项任务状态、13项技术验收、数据边界与4项待办/限制 |
| [独立验收记录](stage1_stage2_review_20261114_01/README.md) | 2026-11-15实现基线的指纹、标签、数据库、矩阵/预测和EDA核对 |
| [第二阶段验收表](stage2/requirements_matrix.md) | 按四个部分登记实现、证据及尚未完成的细项 |

第三阶段正式多模型和第四阶段最终交付尚无完整成果，状态见[任务台账](../../docs/project_roadmap.md)。
带日期的文件夹表示产物版本；阅读顺序以本页阶段编号为准。
执行日志、源指纹和历史测量保持其生成时点含义，文档修订不改变已有数值结果。
旧产物恢复位置见[归档清单](../../docs/archive_manifest.json)。
