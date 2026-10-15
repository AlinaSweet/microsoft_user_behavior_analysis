# 第一阶段第 2 项专项复核报告

复核日期：2026-10-15。复核基线：de7dd79571fefb0fac375c9c9f74c9f181ad8cba。依据为用户提供的《微软商城用户行为分析》第 2 页“领域文献调研与技术栈储备”，并核对第 3 阶段的样本划分要求。

## 1. 结论

第二步的文献研究与技术方案达到本项文档交付要求。已有五篇论文笔记、数字平台公开案例、Spark/Dask 对比、模型取舍、26 个候选特征定义和 10 项待执行实验。本次发现四处实施口径需要补充，已修订；没有发现所核对的论文关键数值抄录错误。

此结论表示研究材料和方案已形成，不表示已完成特征计算、模型训练、Spark 对比跑分或全量数据清洗。文件检查也不能替代你本人对论文的理解或导师的独立审核。

## 2. 对照任务要求

| 原任务要求 | 检查结果 | 证据 |
|---|---|---|
| 阅读 3–5 篇经典论文 | 通过：五篇固定版本，含方法、概念公式、结果及局限 | [阅读笔记](../../docs/research/literature_review.md)、[来源清单](../../docs/research/references.json) |
| 梳理核心算法和特征工程范式 | 通过：显式交叉、embedding、候选相关兴趣、兴趣演化、自注意力；26 个候选定义 | [特征设计](../../docs/research/feature_engineering_plan.md) |
| 调研数字平台方案 | 通过：Google Play、阿里巴巴、Microsoft Recommenders 的公开资料；未推断微软商城内部架构 | [技术栈对比](../../docs/research/tech_stack_comparison.md) |
| 比较 Spark/Dask 及模型在亿级数据下的适用性 | 通过：部署、分区、shuffle、内存、数据布局、模型成本与迁移条件；明确估算和实测的区别 | [技术栈对比](../../docs/research/tech_stack_comparison.md) |
| 能指导后续实施 | 已有方案：候选、标签、时间边界、编码、指标和 10 项 planned 实验；本次补齐四处口径 | [实验方案](../../docs/research/experiment_plan.md) |

## 3. 原文复核

本次重新打开五个固定版本原文链接，核对以下关键位置。页码按缓存 PDF 的第 1 页起算；均为论文历史结果，未在本项目复现。

| 论文 | 核对位置 | 核对结果 |
|---|---|---|
| [Wide & Deep v1](https://arxiv.org/pdf/1606.07792v1) | 第 4 页表 1 | AUC 0.726/0.728；3.9% 是相对 Wide 的线上应用获取率增幅 |
| [DeepFM v1](https://arxiv.org/pdf/1703.04247v1) | 第 4 页设置、第 5 页表 2 | Criteo 的 LR/DeepFM AUC 0.7686/0.8007；90%/10% 随机划分 |
| [DIN v4](https://arxiv.org/pdf/1706.06978v4) | 第 6 页 6.3 节、第 7 页表 3 | BaseModel 0.8624、DIN with Dice 0.8871；注明用户加权 AUC 口径 |
| [DIEN v5](https://arxiv.org/pdf/1809.03672v5) | 第 6 页表 2 | Electronics 的 DIN/DIEN 平均 AUC 0.7603/0.7792，重复五次 |
| [BST v1](https://arxiv.org/pdf/1905.06874v1) | 第 4 页表 3、表 4 | 长度 20；DIN/BST AUC 0.7866/0.7894、平均响应 16/20 ms；7.57% 相对 WDL |

五份本地 PDF 的页数、字节数和 SHA-256 均与来源清单一致。自动检查仅确认原页出现数值；表列归属、实验设置、比较基线和结论含义由本次内容复核确认。没有将不同论文的数据集或 AUC 横向排名。

官方技术文档本次重点复核五处：[Dask 最佳实践](https://docs.dask.org/en/stable/dataframe-best-practices.html)、[Spark SQL 调优](https://spark.apache.org/docs/latest/sql-performance-tuning.html)、[Microsoft Recommenders](https://github.com/recommenders-team/recommenders)、[TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)、[TargetEncoder cross fitting](https://scikit-learn.org/stable/auto_examples/preprocessing/plot_target_encoder_cross_val.html)。其余来源沿用来源清单中的前次核对日期，没有声称本次全部重查。

## 4. 已修订的四处口径

| 问题 | 修订内容 | 状态 |
|---|---|---|
| 截点与候选规则不够具体 | 建议首版每天源时间 00:00 预测；活跃用户看过去 7 天，候选看最多 30 天历史；定义候选覆盖率。固定午夜时 hour_of_day 为常量，应剔除 | 已写入实验方案和特征设计 |
| “新用户”与候选覆盖存在歧义 | 区分训练词表未见实体和预测时完全无历史用户；后者不在首版历史交互候选范围，需另建回退候选协议 | 已写入实验方案 |
| 训练拟合与历史更新没有分清 | 词表、编码、标准化、嵌入等只从训练部分拟合并冻结；可观测行为统计允许更新至预测时刻之前 | 已写入实验方案 |
| 任务要求的 7:2:1 不能只写可选 | 分层随机约 7:2:1 登记为第三阶段必做对照，相同用户商品对的快照按组划分并报告实际比例；另做时间回测。完整候选列表的排序指标仅用于保留整组候选的时间回测 | 已写入实验方案和完成报告 |

以上均为后续实施协议，不代表已经生成样本。具体日期仍需第三步的全量时间范围确定；若数据不足以形成完整历史和 7 天标签窗口，应记录限制并调整研究范围。

## 5. 文件与数据核验

本次生成的机器检查结果见 [复核记录 JSON](stage1_step2_audit.json)，包括：

- 五份原文的页数、大小、指纹和原页数值出现检查。
- 26 个不重复的候选特征定义、10 个不重复的 planned 实验编号、5 个 BibTeX 条目。
- 本步 Markdown 的仓库内文件链接、JSON 解析，以及既有交付文件的 Git 跟踪状态。
- 原始 CSV 为 492,264,642 字节，SHA-256 与既有清单一致；本次未修改原始文件。
- 原文缓存和原始数据被 Git 忽略。小型笔记、来源记录和复核报告可同步 GitHub。
- 核对项目环境中的 scikit-learn、XGBoost、LightGBM、Optuna、Spark 和深度学习框架尚未安装，与“调研完成、训练未执行”的描述一致。

工程检查使用项目现有 Quality 流程；代码内容未改变时本地流程可复用相同源码指纹的成功缓存，Git 文件规范仍会检查。云端 Quality 会强制重新运行格式、类型和现有测试。CI 通过只能证明工程检查通过，不能证明论文事实或未来模型效果。

## 6. 后续工作的边界

下一项是第一阶段第 3 项“数据加载与全流程清洗”：确认全量行数、时间覆盖、行为编码、缺失/异常、重复记录含义和类目一致性，再实现跨分区正确的清洗与新 Parquet 产物。26 个特征和 10 项实验目前仍为设计，后续只有实际运行并保存结果后才能登记完成。
