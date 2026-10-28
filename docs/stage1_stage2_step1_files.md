# 第一阶段与第二阶段第1项：逐文件对应清单

整理日期：2026-10-28。项目根目录：`/Users/alina/Desktop/实习/Github`。

**使用方法：先找所属任务，再按“目录＋具体文件”定位。每一行对应一个实际文件；Parquet分片逐个列出。**

## 1. 清单范围和存放状态

- 已验收实现与文档基线：`de015927a28b1a4729251af0ab0f4ede7ae3fab3`。
- 共列出**421个文件**：**246个Git已跟踪文件**和**175个仅本地正式数据文件**。
- 第一阶段四项及第二阶段第1项按任务分组；共用文件和跨任务验收单列，避免重复计算。
- GitHub文件名为可点击链接；仅本地的大数据文件列出完整相对目录和文件名，其来源及指纹见对应catalog或完成报告。
- “本地另有未提交修改”表示云端已提交版本与本地工作区需分开看，不把工作区改动冒充新验收。
- `.gitkeep`是目录占位，研究中的候选特征属于设计，历史未通过报告属于保留证据，均已标注。
- 本清单不枚举`.git/`、`.venv*/`、`.cache/`等运行环境和缓存；教学示例、未提交的第一周周报草稿及本次索引自身不计入421个快照文件。
- 本次核对文件存在、归属、同步状态和Parquet元数据；完整业务质量结论仍引用既有验收，不刷新历史测量。

机器可读的一一对应关系见[文件清单JSON](../data/catalog/stage1_stage2_step1_files.json)。任务完成情况概览见[已完成任务导航](completed_work.md)。

| 所属任务 | 文件数 | 说明入口 |
|---|---:|---|
| 项目共用：任务来源、总导航和目录占位 | 15 | [项目首页](../README.md) |
| 第一阶段第1项：工程环境、版本管理与编码规范 | 66 | [工程完成记录](stage1_completion.md) |
| 第一阶段第2项：文献调研与技术方案 | 10 | [研究阅读导航](research/README.md) |
| 第一阶段第3项：加载、清洗、校验与数据来源 | 122 | [清洗报告](../outputs/reports/stage1_step3/README.md) |
| 第一阶段第3项补充：重复值研究与当前输入策略 | 23 | [重复值策略](duplicate_policy.md) |
| 第一阶段第4项：压缩、Parquet与三维聚合 | 79 | [预处理报告](../outputs/reports/stage1_step4/README.md) |
| 第二阶段第1项：数据库、查询接口与SQL结果 | 50 | [数据库与SQL报告](../outputs/reports/stage2_step1_20261024/README.md) |
| 跨任务验收：最新完整回归与历史证据 | 56 | [最新阶段验收入口](stage1_review.md) |

## 2. 数据版本先对齐

| 数据版本 | 对应目录或文件 | 记录口径 |
|---|---|---|
| 完整有效原记录 | `data/interim/clean_v1/validated/` | 12,256,906条，当前数据库输入 |
| 历史归并事件 | `data/interim/clean_v1/events/` | 6,213,379条，历史四元组归并 |
| 历史压缩事件及三张聚合表 | `data/processed/base_v1/` | 同一历史归并口径 |
| 当前SQLite | `data/processed/analysis_raw_v1/behavior.sqlite` | 保留全部12,256,906条，超过90条/用户小时只标记 |

四元组为用户、商品、行为、完整日期小时。高频和相同四元组都不能直接证明错误采集。

## 3. 项目共用：任务来源、总导航和目录占位

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `项目根目录` | [README.md](../README.md) | 项目首页、运行方式和任务文档入口 | 已纳入GitHub交付基线 |
| `data/interim/` | [.gitkeep](../data/interim/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `data/processed/` | [.gitkeep](../data/processed/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `data/raw/` | [.gitkeep](../data/raw/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `data/summaries/` | [.gitkeep](../data/summaries/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `docs/` | [.gitkeep](../docs/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `docs/` | [business_conventions.md](../docs/business_conventions.md) | 地区、时区假设、计数与金额缺失等共同业务约定 | 已纳入GitHub交付基线 |
| `docs/` | [completed_work.md](../docs/completed_work.md) | 已完成任务、主要目录、数据版本和验收入口总导航 | 已纳入GitHub交付基线 |
| `docs/` | [project_roadmap.md](../docs/project_roadmap.md) | 四阶段17项任务、完成状态与验收顺序 | 已纳入GitHub交付基线 |
| `docs/requirements/` | [project_brief.pdf](../docs/requirements/project_brief.pdf) | 用户提供的项目任务书归档原件 | 已纳入GitHub交付基线 |
| `notebooks/` | [.gitkeep](../notebooks/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `outputs/figures/` | [.gitkeep](../outputs/figures/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `outputs/reports/` | [.gitkeep](../outputs/reports/.gitkeep) | 空目录占位，使Git保留该目录；不代表分析或模型已实现 | 已纳入GitHub交付基线；目录占位，不是分析成果 |
| `outputs/reports/` | [weekly_report_20261019_20261023.md](../outputs/reports/weekly_report_20261019_20261023.md) | 第二周周报原件的归档衔接说明 | 已纳入GitHub交付基线 |
| `outputs/reports/` | [weekly_report_20261019_20261023.pdf](../outputs/reports/weekly_report_20261019_20261023.pdf) | 用户提供的第二周周报PDF归档原件 | 已纳入GitHub交付基线 |

## 4. 第一阶段第1项：工程环境、版本管理与编码规范

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `项目根目录` | [.editorconfig](../.editorconfig) | 编辑器默认缩进、编码和换行约定 | 已纳入GitHub交付基线 |
| `项目根目录` | [.flake8](../.flake8) | flake8代码规范检查参数 | 已纳入GitHub交付基线 |
| `项目根目录` | [.gitattributes](../.gitattributes) | 二进制及附件字节保留规则，避免改写原件 | 已纳入GitHub交付基线 |
| `.githooks/` | [pre-commit](../.githooks/pre-commit) | 提交前调用统一质量检查 | 已纳入GitHub交付基线 |
| `.githooks/` | [pre-push](../.githooks/pre-push) | 推送前调用统一质量检查 | 已纳入GitHub交付基线 |
| `.github/workflows/` | [quality.yml](../.github/workflows/quality.yml) | GitHub Quality自动检查流程 | 已纳入GitHub交付基线 |
| `项目根目录` | [.gitignore](../.gitignore) | 规定虚拟环境、缓存和大型本地数据不进入Git | 已纳入GitHub交付基线 |
| `项目根目录` | [.python-version](../.python-version) | 登记项目Python版本 | 已纳入GitHub交付基线 |
| `项目根目录` | [AGENTS.md](../AGENTS.md) | 后续工程协作、函数说明、编码与复核规则 | 已纳入GitHub交付基线 |
| `configs/` | [dask.yaml](../configs/dask.yaml) | 日常Dask进程、线程、分块及内存设置 | 已纳入GitHub交付基线 |
| `docs/` | [coding_standard_adoption.md](../docs/coding_standard_adoption.md) | 编码规范如何落地到结构、工具和检查流程 | 已纳入GitHub交付基线 |
| `docs/` | [data_management.md](../docs/data_management.md) | 小文件同步与大文件本地登记政策 | 已纳入GitHub交付基线 |
| `docs/` | [github_sync_guide.md](../docs/github_sync_guide.md) | GitHub Desktop首次上传及日常同步操作说明 | 已纳入GitHub交付基线 |
| `docs/` | [stage1_completion.md](../docs/stage1_completion.md) | 第一阶段工程搭建完成记录及实测范围 | 已纳入GitHub交付基线 |
| `docs/standards/` | [coding_standard.pdf](../docs/standards/coding_standard.pdf) | 用户提供的编码规范归档原件 | 已纳入GitHub交付基线 |
| `outputs/figures/` | [github_initial_upload.jpg](../outputs/figures/github_initial_upload.jpg) | 首次GitHub上传的历史截图 | 已纳入GitHub交付基线 |
| `outputs/reports/` | [coding_standard_compliance.json](../outputs/reports/coding_standard_compliance.json) | 编码规范整改时的质量检查结果 | 已纳入GitHub交付基线 |
| `outputs/reports/` | [coding_standard_data_validation.json](../outputs/reports/coding_standard_data_validation.json) | 编码整改后的数据一致性证据 | 已纳入GitHub交付基线 |
| `outputs/reports/coding_standard_validation/` | [environment_check.json](../outputs/reports/coding_standard_validation/environment_check.json) | 编码整改后的环境运行证据 | 已纳入GitHub交付基线 |
| `outputs/reports/` | [engineering_benchmark.json](../outputs/reports/engineering_benchmark.json) | CSV样本分块读取的机器可读资源测量 | GitHub有已提交版本；本地另有未提交修改 |
| `outputs/reports/` | [engineering_benchmark.md](../outputs/reports/engineering_benchmark.md) | 样本分块测量的文字报告及适用范围 | GitHub有已提交版本；本地另有未提交修改 |
| `outputs/reports/` | [environment_check.json](../outputs/reports/environment_check.json) | 早期实际Dask环境、版本及样本读取报告 | GitHub有已提交版本；本地另有未提交修改 |
| `outputs/reports/` | [environment_check_reproduced.json](../outputs/reports/environment_check_reproduced.json) | 重建环境中的实际运行检查结果 | 已纳入GitHub交付基线 |
| `outputs/reports/` | [environment_reproduction.json](../outputs/reports/environment_reproduction.json) | 从新环境安装锁定依赖的一致性记录 | 已纳入GitHub交付基线 |
| `outputs/reports/` | [git_artifact_check.json](../outputs/reports/git_artifact_check.json) | Git文件与大小政策的历史检查记录 | 已纳入GitHub交付基线 |
| `项目根目录` | [pyproject.toml](../pyproject.toml) | 项目及格式、类型、质量工具设置 | 已纳入GitHub交付基线 |
| `项目根目录` | [requirements-dev.in](../requirements-dev.in) | 开发检查工具的直接依赖声明 | 已纳入GitHub交付基线 |
| `项目根目录` | [requirements-dev.txt](../requirements-dev.txt) | 锁定的运行与开发依赖版本 | 已纳入GitHub交付基线 |
| `项目根目录` | [requirements.in](../requirements.in) | 直接运行依赖的范围声明 | 已纳入GitHub交付基线 |
| `项目根目录` | [requirements.txt](../requirements.txt) | 锁定的完整运行依赖版本 | 已纳入GitHub交付基线 |
| `scripts/` | [check_quality.py](../scripts/check_quality.py) | 规则、格式、类型、测试与源码指纹缓存检查 | 已纳入GitHub交付基线 |
| `scripts/` | [check_quality.sh](../scripts/check_quality.sh) | 统一质量检查的Shell入口 | 已纳入GitHub交付基线 |
| `scripts/` | [run_project.sh](../scripts/run_project.sh) | 统一启动环境、清洗、预处理和数据库等命令 | 已纳入GitHub交付基线 |
| `scripts/` | [setup_environment.sh](../scripts/setup_environment.sh) | 创建环境、安装锁定依赖并启用Git hooks | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/` | [__init__.py](../src/user_behavior_analysis/__init__.py) | 主包初始化与项目内临时目录约束 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/` | [__main__.py](../src/user_behavior_analysis/__main__.py) | 支持python -m方式进入统一命令 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/api/` | [__init__.py](../src/user_behavior_analysis/api/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/api/` | [cli.py](../src/user_behavior_analysis/api/cli.py) | 统一命令参数、任务分发与错误反馈；多任务共用 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/` | [artifacts.py](../src/user_behavior_analysis/artifacts.py) | 对外保留数据产物登记接口 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/common/` | [__init__.py](../src/user_behavior_analysis/common/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/common/` | [coding_rules.py](../src/user_behavior_analysis/common/coding_rules.py) | 检查标准工具之外的项目专项编码规则 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/common/` | [constants.py](../src/user_behavior_analysis/common/constants.py) | 项目路径、字段及有界资源常量 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/common/` | [exceptions.py](../src/user_behavior_analysis/common/exceptions.py) | 配置、资源和处理过程的项目异常类型 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/common/` | [local_cache.py](../src/user_behavior_analysis/common/local_cache.py) | 把SQLite排序聚合临时文件限制在项目缓存中 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/common/` | [utils.py](../src/user_behavior_analysis/common/utils.py) | 流式指纹、输出路径校验、时间戳与JSON保存工具 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/` | [config.py](../src/user_behavior_analysis/config.py) | 读取并验证YAML，生成类型明确的运行配置 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [__init__.py](../src/user_behavior_analysis/dao/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [artifact_repository.py](../src/user_behavior_analysis/dao/artifact_repository.py) | 保存数据清单并检查Git文件政策 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [report_repository.py](../src/user_behavior_analysis/dao/report_repository.py) | 保存结构化运行和资源报告 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [source_repository.py](../src/user_behavior_analysis/dao/source_repository.py) | 解析CSV输入路径并保留原值读取样本 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/models/` | [__init__.py](../src/user_behavior_analysis/models/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/models/` | [config_models.py](../src/user_behavior_analysis/models/config_models.py) | Dask、输入、资源与测量配置的数据结构 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/models/` | [report_models.py](../src/user_behavior_analysis/models/report_models.py) | 环境、测量与数据清单的数据结构 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/` | [runtime.py](../src/user_behavior_analysis/runtime.py) | 保留已有运行接口导入位置的兼容层 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [__init__.py](../src/user_behavior_analysis/service/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [benchmark.py](../src/user_behavior_analysis/service/benchmark.py) | 有界CSV样本读取耗时和资源测量 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [environment.py](../src/user_behavior_analysis/service/environment.py) | 检查真实worker、依赖版本与输入样本 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [runtime.py](../src/user_behavior_analysis/service/runtime.py) | 规划并启动带明确资源限制的Dask进程 | 已纳入GitHub交付基线 |
| `tests/` | [__init__.py](../tests/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `tests/integration/` | [__init__.py](../tests/integration/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `tests/integration/` | [test_workers.py](../tests/integration/test_workers.py) | 检查真实Dask进程与资源设置 | 已纳入GitHub交付基线 |
| `tests/unit/` | [__init__.py](../tests/unit/__init__.py) | Python包或测试包初始化标识；按所在层组织导入 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_cli.py](../tests/unit/test_cli.py) | 检查命令输出和预期失败日志 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_coding_rules.py](../tests/unit/test_coding_rules.py) | 检查专项编码规则的独立场景 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_local_cache.py](../tests/unit/test_local_cache.py) | 检查项目内SQLite临时目录约束 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_stage1.py](../tests/unit/test_stage1.py) | 检查输入路径、内存预算及数据文件管理 | 已纳入GitHub交付基线 |

## 5. 第一阶段第2项：文献调研与技术方案

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `docs/research/` | [README.md](../docs/research/README.md) | 五篇论文、技术方案与后续设计的阅读导航 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `docs/research/` | [experiment_plan.md](../docs/research/experiment_plan.md) | 10项后续实验、候选、标签和评估方案；实验待执行 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `docs/research/` | [feature_engineering_plan.md](../docs/research/feature_engineering_plan.md) | 26个候选特征及历史窗口等设计；尚非正式特征表 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `docs/research/` | [literature_review.md](../docs/research/literature_review.md) | Wide & Deep、DeepFM、DIN、DIEN、BST五篇论文笔记 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `docs/research/` | [references.bib](../docs/research/references.bib) | 五篇论文的BibTeX引用条目 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `docs/research/` | [references.json](../docs/research/references.json) | 研究来源、固定版本、核对日期及原文指纹清单 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `docs/research/` | [tech_stack_comparison.md](../docs/research/tech_stack_comparison.md) | Spark/Dask、数字平台案例和模型选型研究 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `outputs/reports/` | [stage1_step2_audit.json](../outputs/reports/stage1_step2_audit.json) | 研究原文、来源、文档、26个特征和10项实验的机器检查证据 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `outputs/reports/` | [stage1_step2_audit.md](../outputs/reports/stage1_step2_audit.md) | 研究内容、论文关键事实及方案的专项复核说明 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |
| `outputs/reports/` | [stage1_step2_research.md](../outputs/reports/stage1_step2_research.md) | 文献调研与技术方案完成报告 | 已纳入GitHub交付基线；调研与设计已完成；后续特征和实验尚待实现 |

## 6. 第一阶段第3项：加载、清洗、校验与数据来源

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `configs/` | [cleaning.json](../configs/cleaning.json) | 清洗、校验和历史四元组归并参数 | 已纳入GitHub交付基线 |
| `data/catalog/` | [clean_v1.json](../data/catalog/clean_v1.json) | 历史归并事件32个Parquet文件的清单 | 已纳入GitHub交付基线 |
| `data/catalog/` | [data_provenance.json](../data/catalog/data_provenance.json) | 用户提供的数据使用声明及业务背景记录 | 已纳入GitHub交付基线 |
| `data/catalog/` | [user_behavior_raw.json](../data/catalog/user_behavior_raw.json) | 原始CSV来源、大小、路径与内容指纹清单 | GitHub有已提交版本；本地另有未提交修改 |
| `data/catalog/` | [validated_records_v1.json](../data/catalog/validated_records_v1.json) | 全部有效原记录62个Parquet文件的清单；当前数据库输入 | 已纳入GitHub交付基线 |
| `data/interim/clean_v1/activity_anomalies/item/` | `part_00000.parquet` | 商品交互次数与IQR/3σ异常标记的Parquet分片；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/activity_anomalies/item/` | `part_00001.parquet` | 商品交互次数与IQR/3σ异常标记的Parquet分片；本分片131,797行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/activity_anomalies/user/` | `part_00000.parquet` | 用户活跃次数与IQR/3σ异常标记的Parquet分片；本分片729行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/conflicting_keys/` | `part_00000.parquet` | 商品类目冲突隔离关系；本批数据没有冲突记录；本分片0行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/events/` | `part_00000.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00001.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00002.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00003.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00004.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00005.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00006.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00007.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00008.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00009.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00010.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00011.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00012.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00013.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00014.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00015.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00016.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00017.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00018.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00019.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00020.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00021.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00022.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00023.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00024.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00025.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00026.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00027.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00028.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00029.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00030.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/events/` | `part_00031.parquet` | 历史四元组归并事件的Parquet分片；该版本合计6,213,379条；本分片13,379行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/interim/clean_v1/` | `run_status.json` | 本地清洗任务运行状态 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00000.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00001.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00002.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00003.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00004.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00005.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00006.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00007.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00008.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00009.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00010.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00011.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00012.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00013.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00014.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00015.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00016.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00017.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00018.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00019.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00020.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00021.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00022.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00023.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00024.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00025.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00026.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00027.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00028.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00029.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00030.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00031.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00032.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00033.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00034.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00035.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00036.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00037.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00038.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00039.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00040.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00041.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00042.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00043.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00044.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00045.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00046.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00047.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00048.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00049.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00050.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00051.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00052.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00053.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00054.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00055.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00056.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00057.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00058.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00059.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00060.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片200,000行 | 仅本地；由数据清单或报告说明 |
| `data/interim/clean_v1/validated/` | `part_00061.parquet` | 全部有效原记录的Parquet分片；当前第二阶段输入，业务四元组允许重复；本分片56,906行 | 仅本地；由数据清单或报告说明 |
| `data/raw/` | `user_behavior.csv` | 原始CSV的只读软链接入口；指向用户提供的12,256,906条原始记录 | 仅本地；由数据清单或报告说明 |
| `docs/` | [cleaning_rules.md](../docs/cleaning_rules.md) | 字段、时间、异常、历史归并及运行规则 | 已纳入GitHub交付基线 |
| `docs/` | [data_provenance.md](../docs/data_provenance.md) | 原始数据来源和已确认的使用范围说明 | 已纳入GitHub交付基线 |
| `outputs/reports/stage1_step3/` | [README.md](../outputs/reports/stage1_step3/README.md) | 本次任务或验收的文字说明与阅读入口 | 已纳入GitHub交付基线；该任务完成时的报告，保留原计数和测量 |
| `outputs/reports/stage1_step3/` | [audit.json](../outputs/reports/stage1_step3/audit.json) | 完整清洗、全局业务键、IQR/3σ、98份产物及前序研究环境的独立核验 | 已纳入GitHub交付基线；该任务完成时的报告，保留原计数和测量 |
| `outputs/reports/stage1_step3/` | [quality.json](../outputs/reports/stage1_step3/quality.json) | 全量清洗的字段校验、历史归并、实体行为及异常诊断统计 | 已纳入GitHub交付基线；该任务完成时的报告，保留原计数和测量 |
| `scripts/` | [audit_cleaning.py](../scripts/audit_cleaning.py) | 独立复核完整清洗结果的命令入口 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/common/` | [event_values.py](../src/user_behavior_analysis/common/event_values.py) | 事件规范值哈希，供清洗、压缩和数据库读回共同核验 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [cleaning_repository.py](../src/user_behavior_analysis/dao/cleaning_repository.py) | 跨块磁盘唯一键归并及有界Parquet导出 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/models/` | [cleaning_models.py](../src/user_behavior_analysis/models/cleaning_models.py) | 清洗请求、分块证据和质量报告的数据结构 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [anomaly_audit.py](../src/user_behavior_analysis/service/anomaly_audit.py) | 从独立次数直方图复算IQR、3σ阈值和标记 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [cleaning.py](../src/user_behavior_analysis/service/cleaning.py) | 调度全量校验、历史归并、质量统计与导出 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [cleaning_integrity.py](../src/user_behavior_analysis/service/cleaning_integrity.py) | 将完整导出事件值与规范关系进行核验 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [data_quality.py](../src/user_behavior_analysis/service/data_quality.py) | 计算全局完整性、实体次数及异常诊断统计 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [dataset_audit.py](../src/user_behavior_analysis/service/dataset_audit.py) | Dask独立扫描完整Parquet的键、空值、实体与行数；预处理共用 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [validation.py](../src/user_behavior_analysis/service/validation.py) | 校验原始标识符、时间和行为值，保留无效原因 | 已纳入GitHub交付基线 |
| `tests/integration/` | [test_cleaning_pipeline.py](../tests/integration/test_cleaning_pipeline.py) | 用合成CSV检查完整清洗命令流程 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_cleaning.py](../tests/unit/test_cleaning.py) | 检查字段校验和跨块业务键处理场景 | 已纳入GitHub交付基线 |

## 7. 第一阶段第3项补充：重复值研究与当前输入策略

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `configs/` | [duplicate_policy.json](../configs/duplicate_policy.json) | 当前保留原记录、超过90条只标记的策略配置 | 已纳入GitHub交付基线 |
| `data/catalog/` | [duplicate_review_20261024.json](../data/catalog/duplicate_review_20261024.json) | 用户材料的文件名映射、来源及SHA-256 | 已纳入GitHub交付基线 |
| `data/interim/duplicate_review_20261024/` | `user_hour_detail.csv.zip` | 用户提供的全量用户小时明细压缩包；与原始CSV独立核验一致 | 仅本地；由数据清单或报告说明 |
| `data/interim/user_hour_distribution_20261023/` | `user_hour_counts.csv.gz` | 682,940个活跃用户小时的原始记录数完整聚合明细 | 仅本地；由数据清单或报告说明 |
| `docs/` | [duplicate_policy.md](../docs/duplicate_policy.md) | 当前重复值与高频记录处理口径及边界 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [README.md](../outputs/reports/duplicate_review_20261024/README.md) | 用户重复值材料、核验结论和文件作用入口 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [analysis_notes.md](../outputs/reports/duplicate_review_20261024/analysis_notes.md) | 用户提供的原始分析说明，保留原内容 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [behavior_dedup_impact.csv](../outputs/reports/duplicate_review_20261024/behavior_dedup_impact.csv) | 用户提供的四种行为在不同计数口径下的影响 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [high_frequency_user_hours.csv](../outputs/reports/duplicate_review_20261024/high_frequency_user_hours.csv) | 补充生成的15,428个超过90条的用户小时待核查清单 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [key_occurrences.csv](../outputs/reports/duplicate_review_20261024/key_occurrences.csv) | 用户提供的四元组出现次数分布 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [key_occurrences_by_behavior.png](../outputs/reports/duplicate_review_20261024/key_occurrences_by_behavior.png) | 用户提供的四元组重复与行为差异图 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [user_hour_bins.csv](../outputs/reports/duplicate_review_20261024/user_hour_bins.csv) | 用户提供的小时记录数分箱分布 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [user_hour_distribution.png](../outputs/reports/duplicate_review_20261024/user_hour_distribution.png) | 用户提供的小时记录数分布图 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [user_hour_distribution.xlsx](../outputs/reports/duplicate_review_20261024/user_hour_distribution.xlsx) | 用户提供的小时分布、重复情况和行为影响工作簿 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [user_hour_distribution_table.png](../outputs/reports/duplicate_review_20261024/user_hour_distribution_table.png) | 用户提供的小时分布表图片 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [user_hour_exact.csv](../outputs/reports/duplicate_review_20261024/user_hour_exact.csv) | 用户提供的逐次数频数分布 | 已纳入GitHub交付基线 |
| `outputs/reports/duplicate_review_20261024/` | [verification.json](../outputs/reports/duplicate_review_20261024/verification.json) | 从原始CSV独立重建后对附件各项计数的核验结果 | 已纳入GitHub交付基线 |
| `outputs/reports/user_hour_distribution_20261023/` | [README.md](../outputs/reports/user_hour_distribution_20261023/README.md) | 同一用户每小时全部原始记录数的统计口径与结果 | 已纳入GitHub交付基线 |
| `outputs/reports/user_hour_distribution_20261023/` | [analysis.json](../outputs/reports/user_hour_distribution_20261023/analysis.json) | 全量用户小时分布、分位数、输入指纹及计数控制 | 已纳入GitHub交付基线 |
| `outputs/reports/user_hour_distribution_20261023/` | [binned_distribution.csv](../outputs/reports/user_hour_distribution_20261023/binned_distribution.csv) | 各次数区间的频数、占比及对应记录数 | 已纳入GitHub交付基线 |
| `outputs/reports/user_hour_distribution_20261023/` | [distribution_chart.png](../outputs/reports/user_hour_distribution_20261023/distribution_chart.png) | 整体分布与累计分布图 | 已纳入GitHub交付基线 |
| `outputs/reports/user_hour_distribution_20261023/` | [exact_distribution.csv](../outputs/reports/user_hour_distribution_20261023/exact_distribution.csv) | 每个整数次数的完整频数、占比和累计分布 | 已纳入GitHub交付基线 |
| `outputs/reports/user_hour_distribution_20261023/` | [user_hour_distribution.xlsx](../outputs/reports/user_hour_distribution_20261023/user_hour_distribution.xlsx) | 概览、分布表、公式和两张可编辑图的工作簿 | 已纳入GitHub交付基线 |

## 8. 第一阶段第4项：压缩、Parquet与三维聚合

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `configs/` | [preprocessing.json](../configs/preprocessing.json) | 事件类型压缩、Parquet与聚合参数 | 已纳入GitHub交付基线 |
| `data/catalog/` | [base_v1.json](../data/catalog/base_v1.json) | 压缩事件及三张聚合表的文件、模式和指纹清单 | 已纳入GitHub交付基线 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00000.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00001.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00002.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00003.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00004.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00005.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00006.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00007.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00008.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00009.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00010.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00011.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00012.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00013.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00014.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00015.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00016.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00017.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00018.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00019.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00020.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00021.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00022.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/item_daily_stats/` | `part_00023.parquet` | 商品日聚合Parquet分片；行为次数、用户数与首末时间；本分片83,584行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/time_hourly_stats/` | `part_00000.parquet` | 小时聚合Parquet分片；行为次数与不同用户、商品数；本分片744行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/user_daily_stats/` | `part_00000.parquet` | 用户日聚合Parquet分片；行为次数、商品数与首末时间；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/aggregates/user_daily_stats/` | `part_00001.parquet` | 用户日聚合Parquet分片；行为次数、商品数与首末时间；本分片2,324行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/` | `benchmark_source.csv` | 与历史事件集同值的规范CSV，供格式读写测量使用 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00000.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00001.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00002.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00003.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00004.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00005.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00006.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00007.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00008.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00009.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00010.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00011.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00012.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00013.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00014.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00015.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00016.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00017.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00018.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00019.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00020.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00021.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00022.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00023.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00024.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00025.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00026.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00027.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00028.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00029.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00030.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片200,000行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/events/` | `part_00031.parquet` | 历史归并事件的类型压缩Parquet分片；六列规范值保持一致；本分片13,379行 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `data/processed/base_v1/` | `run_status.json` | 本地预处理任务运行状态 | 仅本地；由数据清单或报告说明；历史四元组归并口径 |
| `docs/` | [preprocessing_rules.md](../docs/preprocessing_rules.md) | 压缩事件与三维中间表的口径及复现方式 | 已纳入GitHub交付基线 |
| `outputs/reports/stage1_step4/` | [README.md](../outputs/reports/stage1_step4/README.md) | 本次任务或验收的文字说明与阅读入口 | 已纳入GitHub交付基线；该任务完成时的报告，保留原计数和测量 |
| `outputs/reports/stage1_step4/` | [audit.json](../outputs/reports/stage1_step4/audit.json) | 压缩事件六列规范值、三张聚合表全部键和指标及产物指纹的独立核验 | 已纳入GitHub交付基线；该任务完成时的报告，保留原计数和测量 |
| `outputs/reports/stage1_step4/` | [predecessor_cleaning_audit.json](../outputs/reports/stage1_step4/predecessor_cleaning_audit.json) | 前序完整清洗、异常统计与文件指纹复核 | 已纳入GitHub交付基线；该任务完成时的报告，保留原计数和测量 |
| `outputs/reports/stage1_step4/` | [preprocessing.json](../outputs/reports/stage1_step4/preprocessing.json) | 全量压缩、聚合、规范值和存储读取测量结果 | 已纳入GitHub交付基线；该任务完成时的报告，保留原计数和测量 |
| `scripts/` | [audit_preprocessing.py](../scripts/audit_preprocessing.py) | 独立复核压缩事件和全部聚合指标的入口 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [dataset_repository.py](../src/user_behavior_analysis/dao/dataset_repository.py) | 按登记清单校验并分批读取Parquet；数据库模块共用 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [preprocessing_repository.py](../src/user_behavior_analysis/dao/preprocessing_repository.py) | 磁盘全局聚合用户日、商品日与小时统计 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/models/` | [preprocessing_models.py](../src/user_behavior_analysis/models/preprocessing_models.py) | 预处理请求、模式、产物与聚合证据的数据结构 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [aggregate_audit.py](../src/user_behavior_analysis/service/aggregate_audit.py) | Dask独立重算三张聚合表并逐组逐值比较 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [data_encoding.py](../src/user_behavior_analysis/service/data_encoding.py) | 在规范值不变的前提下压缩存储类型 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [preprocessing.py](../src/user_behavior_analysis/service/preprocessing.py) | 调度压缩事件、全局聚合与读回验证 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [storage_benchmark.py](../src/user_behavior_analysis/service/storage_benchmark.py) | 对同值CSV、原Parquet和压缩Parquet进行完整读取测量 | 已纳入GitHub交付基线 |
| `tests/integration/` | [test_preprocessing_pipeline.py](../tests/integration/test_preprocessing_pipeline.py) | 检查压缩事件与三维聚合的完整命令流程 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_aggregate_audit.py](../tests/unit/test_aggregate_audit.py) | 检查总和相同但分组值错误、额外日期等审计负例 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_preprocessing.py](../tests/unit/test_preprocessing.py) | 检查无损类型压缩与登记数据输入保护 | 已纳入GitHub交付基线 |

## 9. 第二阶段第1项：数据库、查询接口与SQL结果

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `data/catalog/` | [analysis_raw_v1.json](../data/catalog/analysis_raw_v1.json) | SQLite位置、行数、指纹、输入及构建代码对应关系 | 已纳入GitHub交付基线 |
| `data/processed/analysis_raw_v1/` | `behavior.sqlite` | 当前完整业务数据库，主表保留12,256,906条有效原记录，约3.78GiB | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `behavior_distribution.csv` | SQL完整CSV输出：四类原始行为数量及占比 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `daily_active.csv` | SQL完整CSV输出：31个自然日的不同活跃用户数 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `funnel_reach.csv` | SQL完整CSV输出：四类行为的用户覆盖人数；不是严格路径转化 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `item_repurchase.csv` | SQL完整CSV输出：跨日期再次出现购买记录的7日复购代理 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `overview.csv` | SQL完整CSV输出：全量记录、用户、商品、类目与时间边界概览 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `popular_categories.csv` | SQL完整CSV输出：热门类目Top50 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `popular_items.csv` | SQL完整CSV输出：热门商品Top50 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `strict_funnel.csv` | SQL完整CSV输出：指定同用户商品严格跨小时漏斗及完整7日随访 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `user_proxy_segments.csv` | SQL完整CSV输出：购买与高频标记的交叉人群；不是金额型RFM | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `user_sequences.csv` | SQL完整CSV输出：682,940个用户小时桶序列及相邻小时差 | 仅本地；由数据清单或报告说明 |
| `data/processed/analysis_raw_v1/sql_results/` | `weekly_active.csv` | SQL完整CSV输出：连续7个自然日的不同活跃用户；首段标覆盖不足 | 仅本地；由数据清单或报告说明 |
| `docs/` | [sqlite_analysis.md](../docs/sqlite_analysis.md) | 数据库关系、索引、导入、查询与业务口径说明 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/` | [README.md](../outputs/reports/stage2_step1_20261024/README.md) | 本次任务或验收的文字说明与阅读入口 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/` | [cloud_delivery.json](../outputs/reports/stage2_step1_20261024/cloud_delivery.json) | 指定实现提交的远程分支、CI链接与交付检查点 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/` | [database.json](../outputs/reports/stage2_step1_20261024/database.json) | 全量数据库构建、六列规范值读回及完整性检查 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/` | [database_audit.json](../outputs/reports/stage2_step1_20261024/database_audit.json) | 682,940个用户小时的10项指标与独立原始参考逐值比较 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/` | [quality.json](../outputs/reports/stage2_step1_20261024/quality.json) | 该次isort、Black、flake8、mypy、pylint及单元/集成测试检查记录 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/` | [sql_analysis.json](../outputs/reports/stage2_step1_20261024/sql_analysis.json) | 11项完整SQL输出的行数、指纹、预览、耗时与计数控制 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [behavior_distribution.csv](../outputs/reports/stage2_step1_20261024/summaries/behavior_distribution.csv) | 适合GitHub的小型完整SQL结果：四类原始行为数量及占比 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [daily_active.csv](../outputs/reports/stage2_step1_20261024/summaries/daily_active.csv) | 适合GitHub的小型完整SQL结果：31个自然日的不同活跃用户数 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [funnel_reach.csv](../outputs/reports/stage2_step1_20261024/summaries/funnel_reach.csv) | 适合GitHub的小型完整SQL结果：四类行为的用户覆盖人数；不是严格路径转化 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [overview.csv](../outputs/reports/stage2_step1_20261024/summaries/overview.csv) | 适合GitHub的小型完整SQL结果：全量记录、用户、商品、类目与时间边界概览 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [popular_categories.csv](../outputs/reports/stage2_step1_20261024/summaries/popular_categories.csv) | 适合GitHub的小型完整SQL结果：热门类目Top50 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [popular_items.csv](../outputs/reports/stage2_step1_20261024/summaries/popular_items.csv) | 适合GitHub的小型完整SQL结果：热门商品Top50 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [strict_funnel.csv](../outputs/reports/stage2_step1_20261024/summaries/strict_funnel.csv) | 适合GitHub的小型完整SQL结果：指定同用户商品严格跨小时漏斗及完整7日随访 | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [user_proxy_segments.csv](../outputs/reports/stage2_step1_20261024/summaries/user_proxy_segments.csv) | 适合GitHub的小型完整SQL结果：购买与高频标记的交叉人群；不是金额型RFM | 已纳入GitHub交付基线 |
| `outputs/reports/stage2_step1_20261024/summaries/` | [weekly_active.csv](../outputs/reports/stage2_step1_20261024/summaries/weekly_active.csv) | 适合GitHub的小型完整SQL结果：连续7个自然日的不同活跃用户；首段标覆盖不足 | 已纳入GitHub交付基线 |
| `scripts/` | [run_sql_analysis.py](../scripts/run_sql_analysis.py) | 执行11项SQL并导出完整CSV和小型报告 | 已纳入GitHub交付基线 |
| `sql/` | [diagnostics.sql](../sql/diagnostics.sql) | 生成用户小时派生统计、高频标记及诊断关系 | 已纳入GitHub交付基线 |
| `sql/` | [indexes.sql](../sql/indexes.sql) | 创建行为表查询索引 | 已纳入GitHub交付基线 |
| `sql/queries/` | [behavior_distribution.sql](../sql/queries/behavior_distribution.sql) | SQL脚本：四类原始行为数量及占比 | 已纳入GitHub交付基线 |
| `sql/queries/` | [daily_active.sql](../sql/queries/daily_active.sql) | SQL脚本：31个自然日的不同活跃用户数 | 已纳入GitHub交付基线 |
| `sql/queries/` | [funnel_reach.sql](../sql/queries/funnel_reach.sql) | SQL脚本：四类行为的用户覆盖人数；不是严格路径转化 | 已纳入GitHub交付基线 |
| `sql/queries/` | [item_repurchase.sql](../sql/queries/item_repurchase.sql) | SQL脚本：跨日期再次出现购买记录的7日复购代理 | 已纳入GitHub交付基线 |
| `sql/queries/` | [overview.sql](../sql/queries/overview.sql) | SQL脚本：全量记录、用户、商品、类目与时间边界概览 | 已纳入GitHub交付基线 |
| `sql/queries/` | [popular_categories.sql](../sql/queries/popular_categories.sql) | SQL脚本：热门类目Top50 | 已纳入GitHub交付基线 |
| `sql/queries/` | [popular_items.sql](../sql/queries/popular_items.sql) | SQL脚本：热门商品Top50 | 已纳入GitHub交付基线 |
| `sql/queries/` | [strict_funnel.sql](../sql/queries/strict_funnel.sql) | SQL脚本：指定同用户商品严格跨小时漏斗及完整7日随访 | 已纳入GitHub交付基线 |
| `sql/queries/` | [user_proxy_segments.sql](../sql/queries/user_proxy_segments.sql) | SQL脚本：购买与高频标记的交叉人群；不是金额型RFM | 已纳入GitHub交付基线 |
| `sql/queries/` | [user_sequences.sql](../sql/queries/user_sequences.sql) | SQL脚本：682,940个用户小时桶序列及相邻小时差 | 已纳入GitHub交付基线 |
| `sql/queries/` | [weekly_active.sql](../sql/queries/weekly_active.sql) | SQL脚本：连续7个自然日的不同活跃用户；首段标覆盖不足 | 已纳入GitHub交付基线 |
| `sql/` | [schema.sql](../sql/schema.sql) | 建立规范核心表及四元组对照等视图 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [database_repository.py](../src/user_behavior_analysis/dao/database_repository.py) | 参数化分批导入、维表一致性、索引与完整性检查 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/dao/` | [sqlite_client.py](../src/user_behavior_analysis/dao/sqlite_client.py) | 只读参数化SQLite查询，返回DataFrame或分批结果 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/models/` | [database_models.py](../src/user_behavior_analysis/models/database_models.py) | 数据库构建请求、SQL参数和结果证据的数据结构 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [database.py](../src/user_behavior_analysis/service/database.py) | 构建数据库并核对全量六列规范值、计数和来源 | 已纳入GitHub交付基线 |
| `src/user_behavior_analysis/service/` | [sql_analysis.py](../src/user_behavior_analysis/service/sql_analysis.py) | 执行全部已注册SQL、流式导出并核对计数控制 | 已纳入GitHub交付基线 |
| `tests/unit/` | [test_database.py](../tests/unit/test_database.py) | 检查原记录保留、90/91边界、导入安全和只读查询 | 已纳入GitHub交付基线 |

## 10. 跨任务验收：最新完整回归与历史证据

| GitHub项目内目录 | 具体文件 | 作用／对应成果 | 存放与内容状态 |
|---|---|---|---|
| `configs/` | [audit.yaml](../configs/audit.yaml) | 完整审计专用资源配置 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `docs/` | [stage1_review.md](../docs/stage1_review.md) | 第一阶段完整验收入口，区分最新和历史记录 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/figures/` | [stage1_review_ci_checkpoint.png](../outputs/figures/stage1_review_ci_checkpoint.png) | 历史第一阶段云端验收检查点截图 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [README.md](../outputs/reports/stage1_audit_20261015_01/README.md) | 本次任务或验收的文字说明与阅读入口 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [audit.json](../outputs/reports/stage1_audit_20261015_01/audit.json) | 串联质量门禁、真实worker环境、完整预处理和前序复核的总报告 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [cloud_delivery.json](../outputs/reports/stage1_audit_20261015_01/cloud_delivery.json) | 指定实现提交的远程分支、CI链接与交付检查点 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [environment.log](../outputs/reports/stage1_audit_20261015_01/environment.log) | 环境检查进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/environment/` | [environment_check.json](../outputs/reports/stage1_audit_20261015_01/environment/environment_check.json) | 真实Dask环境、资源设置及输入样本检查 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [predecessor_cleaning_audit.json](../outputs/reports/stage1_audit_20261015_01/predecessor_cleaning_audit.json) | 前序完整清洗、异常统计与文件指纹复核 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [preprocessing.log](../outputs/reports/stage1_audit_20261015_01/preprocessing.log) | 预处理与前序复核进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [preprocessing_audit.json](../outputs/reports/stage1_audit_20261015_01/preprocessing_audit.json) | 完整事件、三维聚合逐值与产物指纹独立核验 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [quality.json](../outputs/reports/stage1_audit_20261015_01/quality.json) | 该次isort、Black、flake8、mypy、pylint及单元/集成测试检查记录 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_audit_20261015_01/` | [quality.log](../outputs/reports/stage1_audit_20261015_01/quality.log) | 质量门禁及测试进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [README.md](../outputs/reports/stage1_review_20261015_01/README.md) | 本次任务或验收的文字说明与阅读入口 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [audit.json](../outputs/reports/stage1_review_20261015_01/audit.json) | 串联质量门禁、真实worker环境、完整预处理和前序复核的总报告 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [cloud_delivery.json](../outputs/reports/stage1_review_20261015_01/cloud_delivery.json) | 指定实现提交的远程分支、CI链接与交付检查点 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [environment.log](../outputs/reports/stage1_review_20261015_01/environment.log) | 环境检查进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/environment/` | [environment_check.json](../outputs/reports/stage1_review_20261015_01/environment/environment_check.json) | 真实Dask环境、资源设置及输入样本检查 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [management.json](../outputs/reports/stage1_review_20261015_01/management.json) | 该次工程管理、质量缓存和目录约束检查记录 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [predecessor_cleaning_audit.json](../outputs/reports/stage1_review_20261015_01/predecessor_cleaning_audit.json) | 前序完整清洗、异常统计与文件指纹复核 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [preprocessing.log](../outputs/reports/stage1_review_20261015_01/preprocessing.log) | 预处理与前序复核进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [preprocessing_audit.json](../outputs/reports/stage1_review_20261015_01/preprocessing_audit.json) | 完整事件、三维聚合逐值与产物指纹独立核验 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [quality.json](../outputs/reports/stage1_review_20261015_01/quality.json) | 该次isort、Black、flake8、mypy、pylint及单元/集成测试检查记录 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [quality.log](../outputs/reports/stage1_review_20261015_01/quality.log) | 质量门禁及测试进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261015_01/` | [research_recheck.json](../outputs/reports/stage1_review_20261015_01/research_recheck.json) | 论文及研究文档版本、特征和实验设计计数复核 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_01/` | [audit.json](../outputs/reports/stage1_review_20261024_01/audit.json) | 串联质量门禁、真实worker环境、完整预处理和前序复核的总报告 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_01/` | [environment.log](../outputs/reports/stage1_review_20261024_01/environment.log) | 环境检查进程的原始完整日志 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_01/environment/` | [environment_check.json](../outputs/reports/stage1_review_20261024_01/environment/environment_check.json) | 真实Dask环境、资源设置及输入样本检查 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_01/` | [preprocessing.log](../outputs/reports/stage1_review_20261024_01/preprocessing.log) | 预处理与前序复核进程的原始完整日志 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_01/` | [quality.json](../outputs/reports/stage1_review_20261024_01/quality.json) | 该次isort、Black、flake8、mypy、pylint及单元/集成测试检查记录 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_01/` | [quality.log](../outputs/reports/stage1_review_20261024_01/quality.log) | 质量门禁及测试进程的原始完整日志 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_02/` | [audit.json](../outputs/reports/stage1_review_20261024_02/audit.json) | 串联质量门禁、真实worker环境、完整预处理和前序复核的总报告 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_02/` | [environment.log](../outputs/reports/stage1_review_20261024_02/environment.log) | 环境检查进程的原始完整日志 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_02/environment/` | [environment_check.json](../outputs/reports/stage1_review_20261024_02/environment/environment_check.json) | 真实Dask环境、资源设置及输入样本检查 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_02/` | [preprocessing.log](../outputs/reports/stage1_review_20261024_02/preprocessing.log) | 预处理与前序复核进程的原始完整日志 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_02/` | [quality.json](../outputs/reports/stage1_review_20261024_02/quality.json) | 该次isort、Black、flake8、mypy、pylint及单元/集成测试检查记录 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_02/` | [quality.log](../outputs/reports/stage1_review_20261024_02/quality.log) | 质量门禁及测试进程的原始完整日志 | 已纳入GitHub交付基线；历史未通过尝试，保留原始证据 |
| `outputs/reports/stage1_review_20261024_03/` | [README.md](../outputs/reports/stage1_review_20261024_03/README.md) | 本次任务或验收的文字说明与阅读入口 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/` | [audit.json](../outputs/reports/stage1_review_20261024_03/audit.json) | 串联质量门禁、真实worker环境、完整预处理和前序复核的总报告 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/` | [environment.log](../outputs/reports/stage1_review_20261024_03/environment.log) | 环境检查进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/environment/` | [environment_check.json](../outputs/reports/stage1_review_20261024_03/environment/environment_check.json) | 真实Dask环境、资源设置及输入样本检查 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/` | [predecessor_cleaning_audit.json](../outputs/reports/stage1_review_20261024_03/predecessor_cleaning_audit.json) | 前序完整清洗、异常统计与文件指纹复核 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/` | [preprocessing.log](../outputs/reports/stage1_review_20261024_03/preprocessing.log) | 预处理与前序复核进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/` | [preprocessing_audit.json](../outputs/reports/stage1_review_20261024_03/preprocessing_audit.json) | 完整事件、三维聚合逐值与产物指纹独立核验 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/` | [quality.json](../outputs/reports/stage1_review_20261024_03/quality.json) | 该次isort、Black、flake8、mypy、pylint及单元/集成测试检查记录 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_03/` | [quality.log](../outputs/reports/stage1_review_20261024_03/quality.log) | 质量门禁及测试进程的原始完整日志 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |
| `outputs/reports/stage1_review_20261024_04/` | [README.md](../outputs/reports/stage1_review_20261024_04/README.md) | 本次任务或验收的文字说明与阅读入口 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/` | [audit.json](../outputs/reports/stage1_review_20261024_04/audit.json) | 串联质量门禁、真实worker环境、完整预处理和前序复核的总报告 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/` | [environment.log](../outputs/reports/stage1_review_20261024_04/environment.log) | 环境检查进程的原始完整日志 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/environment/` | [environment_check.json](../outputs/reports/stage1_review_20261024_04/environment/environment_check.json) | 真实Dask环境、资源设置及输入样本检查 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/` | [predecessor_cleaning_audit.json](../outputs/reports/stage1_review_20261024_04/predecessor_cleaning_audit.json) | 前序完整清洗、异常统计与文件指纹复核 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/` | [preprocessing.log](../outputs/reports/stage1_review_20261024_04/preprocessing.log) | 预处理与前序复核进程的原始完整日志 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/` | [preprocessing_audit.json](../outputs/reports/stage1_review_20261024_04/preprocessing_audit.json) | 完整事件、三维聚合逐值与产物指纹独立核验 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/` | [quality.json](../outputs/reports/stage1_review_20261024_04/quality.json) | 该次isort、Black、flake8、mypy、pylint及单元/集成测试检查记录 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `outputs/reports/stage1_review_20261024_04/` | [quality.log](../outputs/reports/stage1_review_20261024_04/quality.log) | 质量门禁及测试进程的原始完整日志 | 已纳入GitHub交付基线；最新完整回归证据（2026-10-24，79项测试） |
| `scripts/` | [audit_stage1.py](../scripts/audit_stage1.py) | 串联质量、真实环境和完整前序数据复核 | 已纳入GitHub交付基线；历史验收或共用验收入口，以报告日期为准 |

## 11. 第二阶段11项SQL：脚本与结果逐一对应

每个查询的完整CSV都在本地保存。9个小型结果另在GitHub报告目录保留完整副本；两份大型结果不上传。

| 分析内容 | SQL脚本 | 本地完整CSV | GitHub小型完整副本 |
|---|---|---|---|
| 全量记录、用户、商品、类目与时间边界概览 | [overview.sql](../sql/queries/overview.sql) | `data/processed/analysis_raw_v1/sql_results/overview.csv` | [overview.csv](../outputs/reports/stage2_step1_20261024/summaries/overview.csv) |
| 四类原始行为数量及占比 | [behavior_distribution.sql](../sql/queries/behavior_distribution.sql) | `data/processed/analysis_raw_v1/sql_results/behavior_distribution.csv` | [behavior_distribution.csv](../outputs/reports/stage2_step1_20261024/summaries/behavior_distribution.csv) |
| 31个自然日的不同活跃用户数 | [daily_active.sql](../sql/queries/daily_active.sql) | `data/processed/analysis_raw_v1/sql_results/daily_active.csv` | [daily_active.csv](../outputs/reports/stage2_step1_20261024/summaries/daily_active.csv) |
| 连续7个自然日的不同活跃用户；首段标覆盖不足 | [weekly_active.sql](../sql/queries/weekly_active.sql) | `data/processed/analysis_raw_v1/sql_results/weekly_active.csv` | [weekly_active.csv](../outputs/reports/stage2_step1_20261024/summaries/weekly_active.csv) |
| 热门商品Top50 | [popular_items.sql](../sql/queries/popular_items.sql) | `data/processed/analysis_raw_v1/sql_results/popular_items.csv` | [popular_items.csv](../outputs/reports/stage2_step1_20261024/summaries/popular_items.csv) |
| 热门类目Top50 | [popular_categories.sql](../sql/queries/popular_categories.sql) | `data/processed/analysis_raw_v1/sql_results/popular_categories.csv` | [popular_categories.csv](../outputs/reports/stage2_step1_20261024/summaries/popular_categories.csv) |
| 682,940个用户小时桶序列及相邻小时差 | [user_sequences.sql](../sql/queries/user_sequences.sql) | `data/processed/analysis_raw_v1/sql_results/user_sequences.csv` | 仅本地；报告保存行数、指纹和预览 |
| 四类行为的用户覆盖人数；不是严格路径转化 | [funnel_reach.sql](../sql/queries/funnel_reach.sql) | `data/processed/analysis_raw_v1/sql_results/funnel_reach.csv` | [funnel_reach.csv](../outputs/reports/stage2_step1_20261024/summaries/funnel_reach.csv) |
| 指定同用户商品严格跨小时漏斗及完整7日随访 | [strict_funnel.sql](../sql/queries/strict_funnel.sql) | `data/processed/analysis_raw_v1/sql_results/strict_funnel.csv` | [strict_funnel.csv](../outputs/reports/stage2_step1_20261024/summaries/strict_funnel.csv) |
| 购买与高频标记的交叉人群；不是金额型RFM | [user_proxy_segments.sql](../sql/queries/user_proxy_segments.sql) | `data/processed/analysis_raw_v1/sql_results/user_proxy_segments.csv` | [user_proxy_segments.csv](../outputs/reports/stage2_step1_20261024/summaries/user_proxy_segments.csv) |
| 跨日期再次出现购买记录的7日复购代理 | [item_repurchase.sql](../sql/queries/item_repurchase.sql) | `data/processed/analysis_raw_v1/sql_results/item_repurchase.csv` | 仅本地；报告保存行数、指纹和预览 |

## 12. 从任务到结果的读取顺序

1. 第一阶段第1项：安装与配置 → 工程代码 → 环境和资源报告 → 质量门禁。
2. 第一阶段第2项：研究导航 → 论文笔记与来源 → 技术对比 → 特征和实验设计 → 专项复核。
3. 第一阶段第3项：原始CSV → 校验代码 → 完整有效记录及历史归并事件 → 质量与独立核验；重复值材料另见补充组。
4. 第一阶段第4项：历史归并事件 → 压缩/聚合代码 → 压缩事件与三张中间表 → 预处理和独立核验。
5. 第二阶段第1项：完整有效记录 → 建表/索引/导入代码 → SQLite → 11个SQL脚本 → CSV与核验报告。

**正式特征构建属于第二阶段第2项，尚未完成；本页不把研究设计、SQL描述性分群或教学示例记为正式特征表。**
