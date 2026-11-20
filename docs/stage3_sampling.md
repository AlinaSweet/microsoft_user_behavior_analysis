# 3.1 样本构建与数据集划分

[项目大纲](requirements/project_brief.pdf)要求以用户–商品对未来 7 天是否购买为目标，构建正负样本，执行约 7:2:1 的分层划分，并比较 SMOTE、欠采样和类别权重。实测结论见[验收报告](../outputs/reports/stage3_sampling_v1/README.md)。

## 正负样本与数据边界

- 一行的主键是 `(as_of_time, user_id, item_id)`。候选为截点前 7 天内已有交互的用户–商品组合，特征只读取截点前的历史。
- 未来区间为 `[as_of_time, as_of_time + 7 天)`。同一用户在区间内买过该商品，标签为 1。若整个区间可观测且未发现该对的购买记录，标签为 0。同一用户购买其他商品不改变该对标签。
- 2025 年 12 月 19 日截点的 1,216,917 个候选缺少完整随访，保留空标签。监督数据来自当年 11 月 25 日、12 月 2 日和 12 月 9 日三个已成熟截点。
- 复用第二阶段从原事件独立审计的稠密标签、宽表及三键连接。入口校验源文件、标签和样本的指纹，重新检查七天窗口、目标值、键集合、最近历史时间和输出覆盖。

## 两套自然分布划分

| 协议 | 分配规则 | 用途 |
|---|---|---|
| `time_backtest` | 11 月 25 日训练，12 月 2 日验证，12 月 9 日测试。相邻训练/验证标签结束时刻与下一截点相接 | 评估未来预测，保留每个截点全部候选 |
| `grouped_721` | 将同一用户–商品对的所有截点作为一组，以组内是否至少有一个正例分层。分别使用固定种子哈希排序，并按累计 70%、90% 边界分配 | 对照大纲要求的分层划分，检验类别分布和同对隔离 |

分层比例对组数取整，报告同时列出实际组数、行数和正例率。完全冷启动评估需要另定义分组与候选策略。当前分组约束施加在用户–商品对，用户和商品可分别在多个集合出现。未来预测结论以时间回测为主。

## 类别不平衡对照

使用同一组预先声明的 16 个历史连续比例特征。每套协议分别在自然训练集拟合中位数填补和标准化，训练后冻结。同一协议的四个逻辑回归控制组共用特征、预处理和求解器配置。SMOTE 使用正例最近邻做连续空间插值，生成向量不带真实用户、商品、时间或离散行为序列。 [SMOTE 原始论文](https://doi.org/10.1613/jair.953)

| 策略 | 训练处理 |
|---|---|
| 自然基线 | 保留全部真实行，使用等权 |
| SMOTE | 保留全部真实行，从至多 5 个正例邻居中抽取并插值，增加正例以接近负:正 10:1 |
| 随机欠采样 | 保留全部真实正例，按固定种子无放回抽取负例，令负:正约为 10:1 |
| 类别权重 | 保留全部真实行，通过正类权重将有效负:正质量调到约 10:1，并令平均样本权重为 1 |

验证和测试始终使用真实行及原始类别比例。每套协议按验证集 Average Precision（AP）选择策略；每种训练策略的分类阈值由验证集最大 F1 决定，同分取较高阈值。模型和阈值冻结后才读取测试集做评估。结果同时报告 ROC-AUC、AP、阈值指标、混淆矩阵、Log Loss 和 Brier 分数。训练比例改变后的概率仍需单独验证校准。

## 运行与下游使用

[默认配置](../configs/stage3_sampling.json)和[数据清单](../data/catalog/stage3_samples_v1.json)记录种子、输入列、分割规则和文件指纹。原始 CSV 全量复现会自动执行本节，见[复现说明](reproduction.md)。

已有第二阶段本地数据时，可复制默认配置到 `.cache/stage3_recheck.json`，把 `data_root`、`report_dir`、`catalog` 改为各自独立且尚未存在的路径。例如 `data/processed/stage3_samples_v2`、`outputs/reproduction/stage3_samples_v2` 和 `outputs/reproduction/stage3_samples_v2_catalog.json`。然后在仓库根目录执行。

macOS 或 Linux

```bash
PYTHONPATH=src .venv/bin/python scripts/run_stage3_sampling.py --config .cache/stage3_recheck.json
```

Windows PowerShell

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\run_stage3_sampling.py --config .cache\stage3_recheck.json
```

每套协议输出 `train.parquet`、`validation.parquet` 和 `test.parquet`，含三键、窗口列、目标和控制实验使用的 16 列。后续建模可按三键回接已验收的第二阶段样本层，按所用划分重新拟合变换。自然分布数据集供所有策略共用。可复现的采样函数、拟合变换和逻辑回归控制模型已登记，Parquet 与模型留在本地。
