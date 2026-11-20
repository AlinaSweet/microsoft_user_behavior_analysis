# 微软商城用户行为分析

**[打开在线EDA看板](https://alinasweet.github.io/microsoft_user_behavior_analysis/)** · 无需安装Python或启动本机服务。

围绕用户购买行为，按数据工程、特征工程与探索分析、模型构建、成果交付四个阶段开展项目。
任务定义见[项目大纲](docs/requirements/project_brief.pdf)，17项任务的状态见[任务台账](docs/project_roadmap.md)。
本仓库已交付第一阶段成果、第二阶段核心成果，以及第三阶段 3.1 样本构建与 3.2 传统模型。跨截点特征稳定性专项与大规模压力验证仍列在任务台账中。

克隆后使用 Git 和 Python 3.12。按[复现说明](docs/reproduction.md)安装锁定依赖，再运行
`python scripts/reproduce.py verify` 检查代码、测试、Excel 导出和在线看板构建。
全量数据和模型实验使用带指纹的原始 CSV，并在独立目录重新生成。

## 阅读顺序与全部文件

| 入口 | 内容 |
|---|---|
| [按阶段逐文件导航](docs/files_by_stage.md) | 按阶段和任务展开全部Git文件，逐个说明用途和文件类型 |
| [可筛选文件与依赖清单](docs/file_inventory.csv) | 与逐文件导航一致，附所属任务、状态、直接导入或参考依赖 |
| [物理目录与数据依赖](docs/repository_map.md) | 解释代码、配置、数据、文档和结果如何协作 |
| [复现说明](docs/reproduction.md) | 安装、数据生成、特征、分析和验收命令 |

## 第一阶段：数据工程体系搭建与理论储备

### 1.1 工程化环境与版本管理搭建

建立可复现的Python环境、资源调度、模块化目录、代码规范以及feature→dev→main版本管理流程。

- 方法：[工程管理](docs/stage1_completion.md)、[编码规范落实](docs/coding_standard_adoption.md)、[Git同步](docs/github_sync_guide.md)、[数据管理](docs/data_management.md)。
- 实现：requirements*.txt、pyproject.toml、[Dask配置](configs/dask.yaml)、[环境安装](scripts/setup_environment.sh)、[质量检查](scripts/check_quality.sh)、.githooks/、.github/。
- 结果：[环境检查](outputs/reports/environment_check.json)、[工程基准](outputs/reports/engineering_benchmark.md)、[第一阶段验收](outputs/reports/stage1/audit.json)。
- 状态：已完成，工程规则持续用于后续阶段。

### 1.2 领域文献调研与技术栈储备

整理5篇行为预测与推荐论文、数字平台案例及Spark/Dask、模型和特征方案，明确方法适用条件。

- 方法与材料：[研究目录](docs/research/README.md)、[文献笔记](docs/research/literature_review.md)、[技术比较](docs/research/tech_stack_comparison.md)。
- 方案：[特征工程计划](docs/research/feature_engineering_plan.md)、[实验计划](docs/research/experiment_plan.md)。
- 结果：[研究成果](outputs/reports/stage1_step2_research.md)、[研究验收](outputs/reports/stage1_step2_audit.md)。
- 状态：研究成果已完成；论文效果和方案设计不作为本项目已完成的模型实验。

### 1.3 数据加载与全流程清洗

对12,256,906条记录分块加载，检查字段、标识、行为、时间及全局质量，记录异常活跃和重复频数。
当前保留全部有效记录；每用户每小时超过90条仅标记。同小时相同字段不能直接认定错误重复。

- 方法：[数据来源](docs/data_provenance.md)、[清洗规则](docs/cleaning_rules.md)、[重复值政策](docs/duplicate_policy.md)、[业务口径](docs/business_conventions.md)。
- 实现：[清洗配置](configs/cleaning.json)、[保留政策](configs/duplicate_policy.json)、[独立清洗审计](scripts/audit_cleaning.py)。
- 结果：[清洗验收](outputs/reports/stage1_step3/README.md)、[客户小时分布与频数](outputs/reports/duplicate_review_20261024/README.md)、[全部有效记录入口](data/catalog/validated_records_v1.json)。
- 状态：当前实际规模完成；一亿条以上压力验证尚未执行。

### 1.4 数据预处理与中间表构建

压缩字段类型，转换为Parquet，并构建用户、商品、时间三个维度的基础聚合。
当前base_raw_v2保存全部原始记录与四元组频数；旧base_v1属于历史归并口径对照。

- 方法：[预处理规则](docs/preprocessing_rules.md)。
- 实现：[预处理配置](configs/preprocessing.json)、[独立预处理审计](scripts/audit_preprocessing.py)、[全记录基表生成](src/user_behavior_analysis/service/feature_base.py)。
- 结果：[原始测量](outputs/reports/stage1_step4/README.md)、[当前全记录基表清单](data/catalog/base_raw_v2.json)。
- 状态：已完成；基础聚合继续作为第二阶段预计算输入。

## 第二阶段：深度特征工程与多维度探索性分析

### 2.1 SQLite数据库搭建与SQL基础分析

建立行为事实表和用户、商品、时间维表，配置索引、分批导入与Python只读查询接口。
11项SQL覆盖行为占比、日活/周活、商品类目排名、序列、漏斗、分群和复购代理。

- 方法：[SQLite设计与分析](docs/sqlite_analysis.md)。
- 实现：[表结构](sql/schema.sql)、[索引](sql/indexes.sql)、[查询集](sql/queries/)、[Python接口](src/user_behavior_analysis/dao/sqlite_client.py)。
- 结果：[数据库及SQL成果](outputs/reports/stage2_step1_20261024/README.md)、[数据库清单](data/catalog/analysis_raw_v1.json)。
- 状态：已完成。

### 2.2 全维度特征体系构建

构建439个标量和6类逻辑序列，覆盖用户、商品、类目、交互、生命周期、时间、RF代理、漏斗、序列、SVD与共现。
四截点预拼接宽表共4,426,649行，提前完成用户、商品、类目等特征的连接，并检查三键唯一、匹配和源值。

- 方法：[特征体系](docs/feature_system.md)、[中间表设计](docs/intermediate_table_design.md)、[预拼接宽表](docs/prejoined_features.md)。
- 实现：[特征配置](configs/feature_system.json)、[生成入口](scripts/run_features.py)、[宽表审计](scripts/audit_wide_features.py)。
- 结果：[源特征生成](outputs/reports/feature_system_20261029/README.md)、[宽表验收](outputs/reports/prejoined_wide_20261107/README.md)。
- 字典：[正式Excel](outputs/reports/stage2/feature_dictionary.xlsx) · [可搜索HTML](outputs/reports/stage2/feature_dictionary.html) · [JSON](outputs/reports/stage2/feature_dictionary.json)。
- 状态：已完成；源定义、逻辑序列与矩阵表示分别统计。

### 2.3 特征预处理与有效性验证

以“同一用户对同一商品在截点后7天是否出现购买记录”为目标，标签按截点、用户、商品三键与宽表对齐。
仅用训练集进行画像、缺失/方差筛选、相关性与互信息、填充、编码、缩放及投影。
保留207个标量，保护40个非恒定RF/漏斗字段；最终生成259列冻结矩阵，并完成分组LR及编码对照。

- 方法：[标签、分组筛选与消融](docs/feature_validation.md)、[目标编码与稀疏预嵌入](docs/stage2_preprocessing.md)。
- 实现：[验证配置](configs/feature_validation.json)、[交付配置](configs/stage2_delivery.json)、[监督验证入口](scripts/run_feature_validation.py)、[预处理入口](scripts/run_stage2_completion.py)。
- 结果：[第一轮分组实验](outputs/reports/feature_validation_20261114/README.md)、[编码对照与矩阵](outputs/reports/stage2/README.md)、[数据版本](data/catalog/stage2_complete_v1.json)。
- 状态：主体完成；同一套冻结特征的跨截点、分用户群稳定性专项仍待补。

### 2.4 多维度探索性数据分析

探索行为分布、日活/周活、活跃时段、漏斗、RF代理分群、商品类目、转化周期、复购代理和工作日/周末差异。
支持日期×人群×类目全局重算、商品下钻、CSV导出，并提供10类核心静态图和分组特征评价图。

- 方法：[EDA看板与指标口径](docs/eda_dashboard1.md)、[看板设计参考](docs/requirements/dashboard_outline.pdf)。
- 实现：[看板启动](scripts/run_eda_dashboard.sh)、[前端资源](src/user_behavior_analysis/assets/eda/)、[HTTP服务](src/user_behavior_analysis/api/dashboard_server.py)。
- 结果：[图表](outputs/reports/stage2/figures/)、[统计明细](outputs/reports/stage2/tables/)、[独立核对](outputs/reports/stage2/eda_audit.json)。
- 状态：核心完成；在线版17个已计算视图、指标卡、周末标识、商品类目列及漏斗比率/分母已补齐。没有法定节假日观测，不构造节日实证对照。

## 第三阶段：多模型建模与性能优化

| 大纲部分 | 当前基础与后续工作 |
|---|---|
| 3.1 样本构建与数据集划分 | 已完成。3,209,732 条成熟样本、时间回测、约 7:2:1 分组分层，以及 SMOTE、欠采样、类别权重实测对照 |
| 3.2 传统模型构建与调优 | 已完成。逻辑回归、XGBoost、LightGBM 完成基础训练和 36 次 Optuna 试验，按时间验证 AUC 选型后冻结测试 |
| 3.3 深度模型构建与优化 | LSTM/GRU、DIN、注意力及训练优化待执行 |
| 3.4 模型融合与可解释性 | Stacking、系数/SHAP、错误样本、冷启动与长尾分析待执行 |
| 3.5 业务落地模拟 | 模拟A/B、收益假设和敏感性分析待执行 |

3.1 的样本口径、数据边界和复现入口见[样本构建方法](docs/stage3_sampling.md)，完整指标见[验收报告](outputs/reports/stage3_sampling_v1/README.md)。

3.2 的训练流程见[传统模型方法](docs/stage3_traditional.md)，3.1 复核和三种模型结果见[传统模型验收](outputs/reports/stage3_traditional_v1/README.md)。

## 第四阶段：成果沉淀与项目复盘

| 大纲部分 | 当前基础与后续工作 |
|---|---|
| 4.1 代码工程化封装 | 已有分层Python包、注释和测试；完整训练/推理API及示例待建模后收口 |
| 4.2 项目文档与汇报材料 | 已有阶段方法和验收文档；项目总报告、汇报PPT与技术分享PPT待完成 |
| 4.3 项目复盘与总结 | 完整流程的问题、解决、局限及优化总结待完成 |
| 4.4 成果提交与展示 | 代码与阶段成果持续同步；最终版本发布及展示待完成 |

## 运行、验收与数据边界

```bash
bash scripts/setup_environment.sh
bash scripts/run_eda_dashboard.sh
```

在线浏览请点击[EDA看板](https://alinasweet.github.io/microsoft_user_behavior_analysis/)。在线版提供17个全量计算视图，支持图表切换及CSV导出；任意日期、人群、类目组合及商品下钻使用本地版 http://127.0.0.1:8765 ，需要本机数据与运行中的Python服务。发布与更新见[看板说明](docs/eda_dashboard1.md)。

```bash
bash scripts/check_quality.sh --force
```

[第一二阶段成果与验收报告](outputs/reports/stage1_stage2_review_20261114_01/completion_report.md)按8个任务汇总结论与待补事项；[第二阶段技术验收表](outputs/reports/stage2/requirements_matrix.md)列出细项证据。
157项测试和数值重放通过属于2026-11-15验收基线，后续文档整理与实现变更分别登记。

实际数据覆盖2025-11-18至12-18，共10,000名用户、2,876,947个商品、8,916个类目，精确到小时。
没有金额、订单、曝光、分钟秒和真实会话；使用RF/购买记录代理，不推算真实GMV、订单量、CTR或在线时长。
大型CSV、Parquet、SQLite、标签、矩阵及模型保留在本地，Git同步代码、配置、文档、小型结果和版本清单。
历史归并结果与原始测量保留其口径；[归档清单](docs/archive_manifest.json)记录已移出工作树的旧产物。

仓库精简记录见[2026-11-17归档清单](docs/repository_cleanup_20261117.json)。未被数值审计引用的运行日志与旧上传截图已可恢复归档；原始数据、代码、模型结果和冻结证据保留。
