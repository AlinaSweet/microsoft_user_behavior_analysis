# 技术栈与数字平台方案对比

调研日期：2026-10-14。工具能力依据官方文档；“本项目选择”和资源估算是工程判断，没有执行 Spark 对比跑分或模型训练。

## 1. 数字平台公开案例能借鉴什么

| 公开案例 | 有来源支持的内容 | 本项目可采用的工程做法 |
|---|---|---|
| Google Play | [Wide & Deep 的候选检索、排序与训练/验证/服务流程](https://arxiv.org/pdf/1606.07792v1) | 将候选生成与概率预测分开，保存词表、配置和模型验证记录 |
| 阿里巴巴广告与淘宝推荐 | [DIN](https://arxiv.org/pdf/1706.06978v4)、[DIEN](https://arxiv.org/pdf/1809.03672v5)、[BST](https://arxiv.org/pdf/1905.06874v1) 对历史兴趣和序列建模 | 保留预测时刻前的历史，比较兴趣汇总和序列模型，分别报告效果与成本 |
| Microsoft Recommenders 开源项目 | 提供数据处理、训练、评估等推荐系统实践与样例，含 Spark 相关算法 | 借鉴实验可复现、独立评估和示例组织；它不能证明本 CSV 的来源或微软商城内部技术栈 |

第三项来源：[Microsoft Recommenders 项目及其参考论文](https://github.com/recommenders-team/recommenders)。以上是公开案例，不构成“所有数字平台都使用某一工具”的市场占有率调查，也没有把某平台的数据处理引擎推定为 Spark 或 Dask。

## 2. Spark 与 Dask：按工作负载比较

Spark 采用 driver/executor 架构，可由 Standalone、YARN、Kubernetes 管理集群。[Spark 集群说明](https://spark.apache.org/docs/latest/cluster-overview.html)

Dask 同样可从单机扩展到多机，提供 Python 任务与 DataFrame 工作流；不是“只能单机”的工具。[Dask 部署说明](https://docs.dask.org/en/stable/deploying.html)

| 比较项 | Dask | Spark | 当前项目判断 |
|---|---|---|---|
| 使用方式 | 接近 Pandas 的分区 DataFrame，也可组织 Python 任务 | SQL/DataFrame 与 driver/executor 体系 | 现有 Python 代码更容易沿用 Dask |
| 数据布局 | 分区读写；早筛列、筛行和适度分区很重要 | 分区、统计信息和查询计划共同影响执行 | 先明确 Parquet schema 与分区策略 |
| 大表关联/排序 | 非索引大表 join、set_index 等可能全量 shuffle | 提供 join 策略与 AQE，仍须关注倾斜和数据交换 | 先缩小输入、预聚合，记录交换成本 |
| 内存 | 分区需容纳任务展开和中间结果；persist 需谨慎 | executor、driver、缓存和中间结果均要规划 | 工具并行不等于自动避免内存不足 |
| 流式场景 | 本项目使用离线 Dask DataFrame，未建设流系统 | Structured Streaming 提供流式 DataFrame 能力 | 当前离线 CSV 没有引入流处理的需求 |
| 集群接入 | 可对接现有 Python/Kubernetes 等部署方式 | 若组织已有 Spark 集群，可复用其调度环境 | 有团队基础设施后再评估迁移收益 |
| 亿级数据 | 能否完成取决于分区、算子、倾斜、内存与磁盘 | 同样取决于资源与工作负载，不能按行数保证速度 | 用真实清洗、去重、聚合任务验证 |

表中处理能力依据：[Dask 最佳实践](https://docs.dask.org/en/stable/dataframe-best-practices.html)、[Dask shuffle 说明](https://docs.dask.org/en/stable/dataframe-groupby.html)、[Spark SQL 调优](https://spark.apache.org/docs/latest/sql-performance-tuning.html)、[Structured Streaming](https://spark.apache.org/docs/latest/streaming/index.html)。

**本项目选择。** 当前源文件为 492,264,642 字节，约 469 MiB、约 1,225 万条行为，来自已有工程记录；没有把任务文档的“亿级场景”当成本文件已实测的规模。继续使用 Dask 清洗和聚合、PyArrow/Parquet 保存明细，聚合变小时转 Pandas 做分析。需要多表复杂 SQL、团队已有集群或当前任务在资源预算内无法完成时，再实测 Spark。

本机已有 [样本报告](../../outputs/reports/engineering_benchmark.json)：32/64 MiB 分块、各两次、每次返回 100,000 行，耗时中位数分别为 1.3445/2.4024 秒。这是首分区样本测量，不能外推全量去重成本，也没有 Spark 数据可用于速度排名。

## 3. 亿级数据时真正要计算的资源量

以下均为说明性估算，不是本机实测。

- 1 亿行 × 40 个 float32 特征 × 4 字节 = 16 GB，约 14.9 GiB；尚未包括 ID、索引、标签、编码副本和训练缓存。因此原始 CSV 体积不能代表训练内存。
- 假设商品词表 400 万、embedding 维度 32、float32，单张参数表为 512 MB，约 488 MiB；梯度和优化器状态会进一步增加占用。400 万是任务文档的规模假设，不是当前已测商品基数。
- 普通全量自注意力的注意力矩阵随序列长度平方增长；长度 100 到 200，该部分元素数变为 4 倍。该估算不等于端到端训练时间必然变为 4 倍。
- 分块只能控制部分读取成本，跨块去重、用户序列汇集和大表 join 仍可能发生数据交换或单组集中。

**准备方案。** 在第三步记录读取、校验、去重、聚合、写出各阶段的时间、RSS 观测峰值、输出大小和 worker 重启；检测热门用户/商品造成的倾斜。保持原始数据只读，失败任务从清单中的输入与参数重跑。

## 4. 模型在大数据场景的选择

下表是针对本项目的实验选择，没有宣称某模型普遍最快或最准。

| 模型 | 预期角色 | 亿级场景主要成本/限制 | 本项目优先级 |
|---|---|---|---|
| 逻辑回归 | 可解释参照 | 原始高基数 ID 编码可能膨胀；非线性关系需设计 | 第一批，使用紧凑统计特征和有限类别编码 |
| XGBoost | 表格非线性基线 | 训练矩阵、直方图、线程和分布式数据布局 | 第一批，先抽样再扩展 |
| LightGBM | 表格非线性基线 | 类别基数、叶子数、深度与过拟合 | 第一批，与 XGBoost 用同一数据比较 |
| Wide & Deep / DeepFM | 特征交互补充 | 词表、embedding 和优化器状态 | 可选扩展，不占用前期必做任务 |
| DIN | 候选相关兴趣 | 每个候选都需关联历史，候选数和长度影响成本 | 传统基线之后，项目指定深度模型 |
| GRU/LSTM、DIEN | 顺序与兴趣演化 | 序列组织、状态、辅助任务和时间精度 | 先简易 GRU，再考虑 DIEN |
| BST | 自注意力序列扩展 | 长度、padding、注意力内存和推理成本 | 受控扩展，先用短序列 |

传统模型能力参考：[逻辑回归官方说明](https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression)、[XGBoost 系统论文](https://arxiv.org/abs/1603.02754)、[LightGBM 论文](https://proceedings.neurips.cc/paper_files/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html)。LightGBM 的 histogram、leaf-wise 和类别分裂机制见 [官方 Features](https://lightgbm.readthedocs.io/en/stable/Features.html)。序列模型的方法来源集中在 [论文笔记](literature_review.md)。

XGBoost 提供 Dask 集成，但 Dask 数据能读取不代表普通模型 fit 会自动分布式；需要对应接口和独立内存预算。[XGBoost Dask 官方说明](https://xgboost.readthedocs.io/en/stable/tutorials/dask.html)

## 5. 技术栈储备清单

| 组件 | 当前状态 | 后续使用时点 |
|---|---|---|
| Python 3.12、Pandas、Dask、NumPy、PyArrow | 已安装并锁版本 | 第三、四步数据处理 |
| 配置、Git hooks、Quality CI | 已配置 | 每次修改和同步 |
| SQLite | 下一阶段的存储/查询选择 | 第二阶段数据库任务，先设计索引与导入方案 |
| scikit-learn、XGBoost、LightGBM、Optuna | 本步仅完成调研，未安装/训练 | 第三阶段按实验需要选择并锁版本 |
| 深度学习框架与 DIN/GRU/BST 实现 | 本步仅完成方案 | 先确定硬件、序列方案与依赖兼容性 |
| Spark | 已调研，未安装或跑分 | 满足迁移条件后，用同一任务对比 |

官方网页会更新；本次核对时间和访问版本记录在 references.json。实际运行环境仍以本仓库 requirements*.txt 为准。
