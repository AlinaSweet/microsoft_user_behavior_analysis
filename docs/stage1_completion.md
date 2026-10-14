# 第一阶段第1项完成记录

本记录对应“工程化环境与版本管理搭建”，验证范围为本机工程框架和样本读取。

| 任务 | 已落地内容 | 可核对的证据 |
|---|---|---|
| 分析环境 | Python 3.12、Pandas、Dask、NumPy、PyArrow；直接依赖及全量版本锁定 | requirements.in、requirements.txt、environment_reproduction.json |
| 环境可复现 | 环境安装脚本自动寻找合适解释器；从空虚拟环境重装并比较全部锁定版本 | scripts/setup_environment.sh、environment_reproduction.json |
| 数据路径 | 命令行路径、环境变量和默认路径；读取前校验表头 | runtime.py、针对性测试 |
| 内存与调度 | 显式加载 YAML，创建独立 worker 进程，并限制内存总预算 | environment_check.json、engineering_benchmark.json |
| 模块化目录 | 数据、代码、配置、文档、结果分层 | README.md、src/、configs/ |
| Git 规范 | main/dev/feature 分支约定、规范提交与远程同步流程 | Git 历史、github_sync_guide.md |
| 小型结果同步 | 小型 CSV/JSON/报告可进入 Git，跟踪文件有 10 MiB 检查 | .gitignore、check-git、data_management.md |
| 大型数据登记 | 来源/生成命令、文件大小、SHA-256、共享位置状态 | data/catalog/user_behavior_raw.json、register/verify 命令 |

## 实测和检查

- 11 项工程逻辑检查通过，覆盖数据路径优先级、前导零、错误表头、内存预算、清单真实性和 Git 文件规则。
- 本机创建全新的 .venv-repro 并安装 requirements.txt，全部 23 个锁定版本一致，pip check 通过。
- 新环境通过 USER_BEHAVIOR_CSV 指向真实源文件，成功启动 2 个独立 worker，实际线程数、内存上限及阈值与配置一致。
- 32 MiB、64 MiB 两种 CSV 分块各测两次，每次读取首个分区并返回 100,000 行样本；没有 worker 重启。
- 对原始 CSV 登记内容指纹并执行 verify，文件与清单匹配。
- 所有检查数据保存在本项目目录；虚拟环境、Dask 缓存及临时测试文件由 .gitignore 排除。

## 验证边界

样本测试验证的是环境与起始资源参数，不代表全量数据的最优性能。RSS 为约 0.1 秒间隔的采样观测，可能漏掉更短暂的峰值。更复杂的清洗、聚合、连接操作需要在后续阶段重新测量。

当前原始数据由本机用户提供，清单明确标记 local_only，没有声称数据已上传或已有共享下载地址。后续大型产物写入指定数据目录，登记生成命令；如交付者需要直接下载，再登记团队提供并可访问的共享位置。

文献调研、全量清洗、质量校验业务规则和 Parquet 中间表属于第一阶段后续具体任务。
