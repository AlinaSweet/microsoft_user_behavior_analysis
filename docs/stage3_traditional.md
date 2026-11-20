# 3.2 传统分类模型构建与调优

三种模型使用 3.1 已验收的同一套时间回测样本和 16 个历史比例特征。输入、日期、种子和计算预算已登记。 [阶段 3.1](stage3_sampling.md) · [3.2 实测报告](../outputs/reports/stage3_traditional_v1/README.md)

## 数据与隔离

训练、验证和测试截点依次为 2025-11-25、2025-12-02 和 2025-12-09。训练样本为 1,030,893 条，验证为 1,061,515 条，测试为 1,117,324 条。每个截点的特征只取截点前的历史，标签取截点起连续七天的同对购买行为。输入审核复查全部分区的时间、三键、成熟标签和文件指纹。模型入口固定读取 `time_backtest`。

中位数填补和标准化在完整训练集拟合一次。三种模型共用同样的 16 个输入和预处理。训练保留真实行，通过每个模型搜索的正类权重改变训练目标中的正负质量。权重按训练行归一化为均值 1。验证和测试均使用原始候选与真实类别分布。

## 基础训练与调参

| 模型 | 初始模型 | Optuna 搜索参数 |
|---|---|---|
| 逻辑回归 | L2、LBFGS、C=1、等权 | C、正类权重 |
| XGBoost | CPU histogram、96 棵树、深度 4、学习率 0.08、等权 | 树数、深度、学习率、最小子节点权重、行/列抽样、L2 正则和正类权重 |
| LightGBM | CPU 直方图、96 棵树、31 叶、学习率 0.08、等权 | 树数、叶数、叶最少行数、学习率、行/列抽样、L2 正则和正类权重 |

每个模型运行 12 次完整训练，对同一验证集最大化 ROC-AUC。前四次包含一次预先声明的基线和三次启动采样，其余八次由固定种子的 TPE 采样。每个模型家族保留验证 AUC 最高的试验，平局保留最早完成的候选。在三个家族中也按验证 AUC 冻结获选模型。每个基线和调优模型的分类阈值按验证 F1 最大值选择，平局取较高阈值。 [Optuna TPE 接口](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html)

冻结记录和本地模型保存后，再读取测试数据。最终发布 AUC、准确率、精确率、召回率、F1、AP、Brier、Log Loss、混淆矩阵及全量预测耗时。模型文件重新加载后执行测试评分，输出的概率、标签和样本键逐行读回核验。测试集为既有的历史时间回测，报告解读限于该候选范围和测试窗口。

## 运行与输出

安装锁定的 Python 3.12 环境。macOS 需要 OpenMP 运行库，可用 Homebrew 执行 `brew install libomp`。Linux 和 Windows 使用 CPU 版 XGBoost wheel。 [XGBoost 官方安装](https://xgboost.readthedocs.io/en/stable/install.html) · [LightGBM 官方安装](https://lightgbm.readthedocs.io/en/stable/Installation-Guide.html)

原始 CSV 的完整复现入口会在生成 3.1 后自动运行 3.2。已有本地 3.1 时间样本时，可以复制[默认配置](../configs/stage3_traditional.json)到 `.cache/stage32_recheck.json`，把 `data_root`、`report_dir`、`catalog` 分别改为三个独立、未使用的路径，例如 `data/processed/stage3_traditional_v2`、`outputs/reproduction/stage3_traditional_v2` 和 `outputs/reproduction/stage3_traditional_v2_catalog.json`。

macOS 或 Linux

```bash
PYTHONPATH=src .venv/bin/python scripts/run_traditional_models.py --config .cache/stage32_recheck.json
```

Windows PowerShell

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\run_traditional_models.py --config .cache\stage32_recheck.json
```

汇总报告和调参记录随代码同步。模型、测试概率文件和目录位置按 [3.2 数据清单](../data/catalog/stage3_traditional_v1.json)登记，二进制数据留在本机。
