# 微软商城用户行为分析

本仓库用于用户行为分析实习项目。原始 CSV 约 469 MiB、约 1,225 万行，实际列名为 time、user_id、item_id、item_category、behavior_type。

## 项目结构

```text
configs/                    运行配置
scripts/                    环境安装和统一运行入口
src/user_behavior_analysis/ 主包
  api/                      命令入口与错误反馈
  service/                  资源规划、环境检查与样本测量
  dao/                      CSV 读取、清单登记与报告保存
  models/                   配置、报告与登记请求的数据结构
  common/                   异常、常量、路径校验和规范检查
  config.py                 YAML 加载与配置合法性校验
tests/unit/                 独立逻辑场景测试
tests/integration/          真实 Dask 进程与命令流程测试
.githooks/                  提交和推送前检查
.github/workflows/          GitHub 自动检查
data/raw/                   本机原始数据
data/interim/               大型中间表
data/processed/             标准化数据
data/catalog/               可同步的数据校验清单
data/summaries/             可同步的小型中间统计表
docs/                       项目说明
notebooks/                  后续探索性分析
outputs/reports/            检查报告和小型结果
outputs/figures/            图表
.cache/                     本机运行缓存
```

## 第一次准备环境

在终端进入项目目录：

```bash
cd '/Users/alina/Desktop/实习/Github'
bash scripts/setup_environment.sh
```

脚本会优先识别现有虚拟环境的 Python 3.12，再尝试 python3.12 和本机已安装的 Codex Python 路径，因此本机不需要先配置 python3.12 这个命令。

换到其他机器时先安装 Python 3.12；若脚本找不到解释器，明确指定其路径：

```bash
PYTHON_BIN='/完整路径/python3.12' bash scripts/setup_environment.sh
```

脚本创建或使用项目 .venv，按 requirements-dev.txt 安装锁定的运行依赖和五种代码检查工具，运行 pip check，并启用 Git 提交/推送检查。requirements.txt 保留纯运行依赖锁；requirements.in、requirements-dev.in 记录直接依赖范围；.python-version 记录本次使用的 3.12.14，文件自身不会安装 Python。

## 运行环境和资源检查

```bash
bash scripts/run_project.sh check
bash scripts/run_project.sh benchmark
```

check 真正启动 Dask 进程 worker，检查生效的内存阈值、线程数和内存上限，并读取 1,000 行原始样本。benchmark 对 32 MiB 和 64 MiB CSV 分块各执行两次，返回每次 100,000 行样本，记录耗时和 worker RSS。报告保存到 outputs/reports/。

benchmark 每次解析首个 CSV 分区，再返回设定数量的行，属于样本资源验证；全量处理性能需要在后续数据处理任务中另行评估。

## 指定数据位置

数据路径优先级是：命令行 --data → USER_BEHAVIOR_CSV 环境变量 → configs/dask.yaml 的默认路径。相对路径按项目根目录解释。

当前默认 data/raw/user_behavior.csv 已链接到本机原始文件。换电脑或换位置时，可以选择以下任意一种方式：

```bash
bash scripts/run_project.sh check --data '/完整路径/user_behavior.csv'
USER_BEHAVIOR_CSV='/完整路径/user_behavior.csv' bash scripts/run_project.sh check
```

读取前检查表头；ID 和原始行为值使用 Arrow 字符串，保留可能存在的前导零。本阶段不进行清洗或业务转换。

## 资源配置怎样生效

程序显式加载 configs/dask.yaml，把 distributed 部分交给 Dask，并按 local_cluster 部分启动 LocalCluster。进程数、线程数、内存上限和 CSV 分块大小因此被实际使用。

默认最多 2 个 worker、每个 1 个线程、每个最多 1 GiB 内存。启动时重新查看可用内存，把所有 worker 的内存总预算限制为可用内存的 70%；不足时自动减少 worker 或降低内存上限。连 512 MiB 的单个 worker 都无法安排时会停止并提示关闭其他应用。

缓存和溢写数据保存到本项目 .cache/dask。内存阈值采用 60% managed data 溢写、70% 进程内存溢写、80% 暂停新任务、95% 触发 nanny 重启机制，详见 [Dask 官方说明](https://distributed.dask.org/en/stable/worker-memory.html)。样本报告用于验证起始参数，不能保证任何未来任务都不会内存不足。

## 数据与结果同步

小型 CSV、JSON、报告和图表可以进入 Git；原始数据和大型中间表保留在对应数据目录，并用 data/catalog 的校验清单记录大小、SHA-256 和获取/生成方式。具体规则见 [数据管理说明](docs/data_management.md)。

```bash
bash scripts/run_project.sh check-git
```

## Git 与 GitHub Desktop

远程仓库：[microsoft-store-user-behavior-analysis](https://github.com/AlinaSweet/microsoft-store-user-behavior-analysis)（私有）。

- main：稳定版本与里程碑。
- dev：集成和日常开发。
- feature/<任务名称>：从 dev 创建，完成后合并回 dev。
- Commit Message：类型: 简短说明，类型包括 feat、fix、docs、data、refactor、chore。

首次发布和日常 Commit、Push 步骤见 [同步操作说明](docs/github_sync_guide.md)。

## 编码规范和每次改动后的检查

执行 [编码规范原文](docs/standards/coding_standard.pdf)，落地规则见 [AGENTS.md](AGENTS.md) 和 [整改说明](docs/coding_standard_adoption.md)。

```bash
# 自动整理格式，并执行所有检查
bash scripts/check_quality.sh --format

# 只检查；代码和工具版本未变且上次成功时复用结果
bash scripts/check_quality.sh

# 强制重新执行全部检查
bash scripts/check_quality.sh --force
```

检查包括 PDF 专项规则、isort、Black、flake8、mypy、pylint、单元/集成测试和 Git 文件政策。详细日志在 .cache/quality/，可交付记录在 outputs/reports/coding_standard_compliance.json。

Git 提交和推送会调用同一入口；GitHub 每次推送 main/dev/feature 分支或提交 Pull Request 时也会检查。合入前先检查改动，再确认 Quality 通过。当前通过项目约定和本地 hooks 执行，未配置 GitHub 服务端分支保护。

测试使用临时合成数据，覆盖路径优先级、前导零、错误表头、配置校验、内存规划、清单指纹、文件同步政策和真实 worker 启动。它们不会改写原始 CSV 或历史实测报告。

工程搭建的验收内容和实测边界见 [第一阶段第1项完成记录](docs/stage1_completion.md)。
