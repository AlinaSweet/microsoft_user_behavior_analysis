# 微软商城用户行为分析

基于12,256,906条用户行为记录，完成工程化数据处理、数据库、特征体系、训练期预处理与探索分析。
第一阶段已在当前数据规模完成；第二阶段核心成果已落地，跨截点稳定性专项和看板展示细项待补。第三阶段正式建模与第四阶段交付按[任务台账](docs/project_roadmap.md)推进。

最新逐项结论见[第一二阶段完成与复核报告](outputs/reports/stage1_stage2_review_20261114_01/completion_report.md)，日期2026-11-15。

## 阅读入口

| 想了解什么 | 当前文件 |
|---|---|
| 第二阶段结果、图表与洞察 | [完整交付报告](outputs/reports/stage2/README.md) |
| 老师要求如何落实 | [逐项验收对照](outputs/reports/stage2/requirements_matrix.md) |
| 所有目录与文件依赖 | [仓库地图](docs/repository_map.md) |
| 当前特征、公式和筛选原因 | [Excel字典](outputs/reports/stage2/feature_dictionary.xlsx) · [可搜索HTML](outputs/reports/stage2/feature_dictionary.html) |
| 当前数据版本 | [数据入口](data/catalog/current_datasets.json) |
| 第一阶段最新复核 | [说明](docs/stage1_review.md) · [完整证据](outputs/reports/stage1/audit.json) |

## 第二阶段四部分

| 部分 | 成果与方法 |
|---|---|
| 数据库与SQL | [SQLite、索引、11项SQL及Python接口](docs/sqlite_analysis.md)；[全量结果](outputs/reports/stage2_step1_20261024/README.md) |
| 特征构建 | [439标量＋6类逻辑序列](docs/feature_system.md)；[用户/商品/类目等预拼接宽表](docs/prejoined_features.md)，四截点4,426,649行 |
| 预处理与验证 | [对级未来7天标签、分组筛选与消融](docs/feature_validation.md)；[目标编码和稀疏预嵌入](docs/stage2_preprocessing.md)，259列冻结矩阵 |
| 多维EDA | [看板一使用与口径](docs/eda_dashboard1.md)；全局筛选、下钻、CSV与[静态图](outputs/reports/stage2/figures/) |

## 启动与检查

```bash
bash scripts/setup_environment.sh
bash scripts/run_eda_dashboard.sh
```

在浏览器打开 http://127.0.0.1:8765 。看板需要本机数据和运行中的Python服务；GitHub展示源代码与报告。
环境、数据生成和核验命令见[复现说明](docs/reproduction.md)。

```bash
bash scripts/check_quality.sh --force
```

质量检查包括规范、格式、类型、静态分析、单元/集成测试和Git文件政策。
Git流程为feature → dev → main，合入前完成检查与远程Quality CI；见[同步说明](docs/github_sync_guide.md)。

## 数据与结论边界

原记录全部保留，每用户小时超过90条仅标记；原始计数与不同四元组计数并存。
数据为2025-11-18至12-18、10,000名用户的31天观测；同小时内顺序不可识别。
主预测目标是截点后7天同一用户对同一商品是否有购买记录，三键严格对齐；用户级购买单独分析。
没有金额、订单或曝光，采用已确认的RF/购买次数代理，不能推算真实GMV、订单量或CTR。
当前是历史回测与固定LR预实验，尚不能说明未来线上收益。

大型原始数据、Parquet、SQLite、矩阵及模型留在本地，Git同步代码、配置、方法、字典、小型结果和校验清单。
旧报告已按[归档清单](docs/archive_manifest.json)移出工作树，可从本机归档或Git历史恢复；当前入口只指向有效成果。
