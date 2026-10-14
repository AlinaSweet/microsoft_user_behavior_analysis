# 微软商城用户行为分析

本仓库用于微软商城用户行为分析实习项目。原始 CSV 当前约 469 MiB、约 1,225 万行，包含 `time`、`user_id`、`item_id`、`item_category`、`behavior_type` 五列。

## 项目结构

```text
configs/                   Dask 与运行配置
data/raw/                  原始数据（本地挂载，不纳入 Git）
data/interim/              中间数据
data/processed/            标准化数据
docs/                      项目文档
notebooks/                 探索性分析笔记本
outputs/figures/           图表
outputs/reports/           报告和小型交付结果
src/user_behavior_analysis/ 可复用 Python 代码
```

数据、代码、文档和结果分开放置。原始数据和大型生成数据不直接提交到 Git；小型报告、配置和可复现代码可提交。若需要共享大型数据产物，先采用 Git LFS、DVC 或团队指定的数据存储。

## 环境

项目使用 Python 3.12。创建并启用虚拟环境：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.in` 记录直接依赖范围，`requirements.txt` 锁定本次解析出的完整版本。当前工作区已将 `data/raw/user_behavior.csv` 链接到本机原始文件；该链接目标和原始数据均不会进入 Git。其他机器可将 CSV 放在该路径，或通过 `USER_BEHAVIOR_CSV` 环境变量提供文件路径。

## Git 分支与提交

- `main`：稳定版本与里程碑。
- `dev`：集成和日常开发分支。
- `feature/<简短名称>`：从 `dev` 创建的单项功能分支，完成后合并回 `dev`。
- 修复类工作可使用 `fix/<简短名称>`。

提交信息格式：`<类型>: <简短说明>`。类型建议使用 `feat`、`fix`、`docs`、`data`、`refactor`、`chore`，例如 `chore: 初始化分析项目结构`。

## 数据处理约定

- 先用小样本确认字段类型、缺失值和处理逻辑，再处理全量数据。
- CSV 全量约 469 MiB，读取时优先使用分块或 Dask；不要默认一次性将所有列读成 Python 字符串对象。
- Dask 本地调度起始配置为 2 个 worker、每个 1 个线程和 1 GiB 内存上限，CSV 分块为 64 MiB；该起点按本机 16 GiB 总内存、配置时约 3 GiB 可用内存制定。每次全量运行前先检查可用内存，再按机器状态调整 `configs/dask.yaml`。
- 中间数据优先写成 Parquet，并记录处理参数、输入文件标识和行数等元数据。
