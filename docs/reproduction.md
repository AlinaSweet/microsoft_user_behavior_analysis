# 运行、复现与核验

## 从干净的 Git 克隆开始

安装 Git 和 Python 3.12，在克隆的仓库根目录运行以下命令。验证包括依赖、代码规范、全套测试、在线看板构建和 Excel 字典导出。

macOS 或 Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/reproduce.py verify
```

Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/reproduce.py verify
```

仅重建在线 EDA 时可以直接用 Python 3.12 运行 `python scripts/reproduce.py pages`。
输出位于 `_site`，可用 `python -m http.server --bind 127.0.0.1 --directory _site 8000` 预览。

## 从原始 CSV 重建第一、二阶段和 3.1

取得 [数据清单](../data/catalog/user_behavior_raw.json) 对应的原始 CSV。命令校验字节数和 SHA-256，再在独立的新目录克隆当前提交并复制原始 CSV。完整运行需要足够磁盘保存 SQLite、Parquet 和模型中间结果，建议预留至少 30 GB。

重绘中文静态图表时，Matplotlib 从系统已安装的中文字体中选择。缺少中文字体的环境可以安装 Noto Sans CJK SC。

在上述虚拟环境中执行，或将 `python` 替换为上面对应平台的虚拟环境解释器。

```text
python scripts/reproduce.py full --csv "原始 user_behavior.csv 的路径" --destination ".cache/reproduced"
```

命令依次生成清洗结果、数据库、SQL、EDA、特征、标签、固定逻辑回归、矩阵验收，以及 3.1 的分组划分和不平衡对照。3.1 读取本次新建的对级样本。新版本的验收和字典位于新克隆的 `outputs/reproduction`。大型数据和模型位于新克隆的 `data`。冻结的旧报告仍可按其记录的提交追溯，运行性能和二进制产物的字节指纹随平台与运行环境变化。

## 分阶段运行和复核

以下工程脚本使用 Bash 包装器。若直接用 Python 调用各阶段脚本，请将 `PYTHONPATH` 指向当前仓库的 `src`。原始 CSV 可从 `data/raw/user_behavior.csv` 或 `USER_BEHAVIOR_CSV` 接入。

| 内容 | 入口 |
|---|---|
| 环境/资源 | bash scripts/run_project.sh check；benchmark |
| 清洗/预处理历史基线 | bash scripts/run_project.sh clean；preprocess；具体参数见各方法文档 |
| 数据库 | bash scripts/run_project.sh database，参数见sqlite_analysis.md |
| SQL | PYTHONPATH=src .venv/bin/python scripts/run_sql_analysis.py |
| 全记录特征 | PYTHONPATH=src .venv/bin/python scripts/run_features.py --phase all |
| 预拼接审计 | scripts/audit_wide_features.py，参数见prejoined_features.md |
| 对级标签与第一轮筛选 | scripts/run_feature_validation.py，参数见feature_validation.md |
| 3.1 样本划分与不平衡对照 | scripts/run_stage3_sampling.py，参数见[样本构建](stage3_sampling.md) |
| 当前新增预处理/实验/报告/重放 | PYTHONPATH=src .venv/bin/python scripts/run_stage2_completion.py --phase all |
| 本地交互EDA | bash scripts/run_eda_dashboard.sh |
| GitHub在线EDA | https://alinasweet.github.io/microsoft_user_behavior_analysis/ |
| 生成静态发布目录 | python scripts/reproduce.py pages |
| 全部代码检查 | python scripts/reproduce.py verify |

不同版本必须复制对应config并设置全新的输出目录/catalog，然后用--config指定。
已登记当前版本不允许原地重建；流水线拒绝覆盖，避免改写测试结果或历史证据。
第二阶段新流程顺序为prepare→experiments→reports→audit；报告读取data/summaries/eda_support_v1的冻结补充证据。
分组相关性用最多100,000条训练候选的确定性样本；模型训练与矩阵/预测核验覆盖完整候选。
补充证据CSV与feature_evidence.json来自已验收全量EDA，manifest给出来源提交与SHA；它们不参与模型拟合。

用锁定的 Python 环境从当前 JSON 导出 Excel，指定新的输出路径。

```text
python scripts/export_feature_dictionary.py --output .cache/feature_dictionary.xlsx
```

第一阶段新复核须使用未存在目录：

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_stage1.py \
  --output-dir outputs/reports/stage1_audit_YYYYMMDD_NN
```

完整数据控制：scripts/audit_current_data.py；原特征工件：scripts/audit_feature_delivery.py。
它们不改变原CSV、特征数值或标签；新输出与当前catalog指纹有变更时必须登记为新版本。
