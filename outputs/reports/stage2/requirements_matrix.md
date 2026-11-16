# 第二阶段技术验收表

依据[项目大纲](../../../docs/requirements/project_brief.pdf)、[看板设计](../../../docs/requirements/dashboard_outline.pdf)及已确认的数据口径，按第二阶段四部分登记。
数值验收基线为2026-11-15，文档整理于2026-11-16。跨截点专项与看板展示细项尚未完成。

## 2.1 SQLite数据库搭建与SQL基础分析

| 验收点 | 状态与实现 | 证据位置 |
|---|---|---|
| 规范化结构、导入、索引 | 已完成：全部有效记录、维表/事实表、参数化批量导入 | sql/schema.sql、indexes.sql；stage2_step1_20261024/database*.json |
| 基础及复杂SQL | 已完成：11项查询、窗口/子查询及Python复核 | sql/queries/；stage2_step1_20261024/sql_analysis.json |
| Python接口 | 已完成：只读参数化查询、分批结果与DataFrame | src/user_behavior_analysis/dao/sqlite_client.py |

## 2.2 全维度特征体系构建

| 验收点 | 状态与实现 | 证据位置 |
|---|---|---|
| 基础与扩展特征 | 已完成：1/3/7/30天窗口、439标量与6类序列 | feature_dictionary.json；data/catalog/features_raw_v2.json |
| RF、漏斗、生命周期、转移与偏好 | 已完成代理口径：跨小时路径、时间衰减、RF/购买记录代理 | docs/feature_system.md；源snapshot质量记录 |
| 隐式和关联特征 | 已完成：训练历史拟合SVD、共现及未知回退 | feature_system_20261029/latent_fit.json；源catalog |
| 文档与计数 | 已完成：445源定义全量保留，207入选、9表示和259矩阵列分别列出 | 当前Excel/JSON/HTML字典 |
| 中间表分层 | 已完成：聚合、实体、预拼接、标签和模型矩阵分别登记 | docs/intermediate_table_design.md；docs/repository_map.md |
| 提前拼接核心特征 | 已完成：4,426,649行；三键唯一、LEFT JOIN及439列逐值控制 | data/catalog/prejoined_wide_v1.json；prejoined_wide_20261107/audit.json |

## 2.3 特征预处理与有效性验证

| 验收点 | 状态与实现 | 证据位置 |
|---|---|---|
| 用户商品对未来7天标签 | 已完成：成熟候选逐行0/1，未成熟为NULL，按截点/用户/商品三键连接 | feature_validation_20261114/samples.json、audit.json；对级标签清单 |
| 标签粒度隔离 | 已完成：用户级目标仅用于独立EDA，不混入对级模型 | eda_mature_example.json；interactive_forward.py |
| 缺失、常量与方差 | 已完成：训练期画像后筛选，低覆盖单独记录 | feature_validation_20261114/selection.json |
| 分组互信息与相关性 | 已完成训练截点：基础/业务/序列/SVD/共现分别评价 | importance_rank.csv、selected_correlations.csv、figures/mi_*与correlation_* |
| 跨截点、分用户群稳定性 | 部分完成：已有训练期分群诊断、跨截点覆盖和模型指标；同一套特征的完整稳定性专项待补 | training_group_diagnostics.json；supplementary_eda.json；综合报告D01 |
| 业务特征保护 | 已完成：40个非恒定RF/漏斗字段保护；常量仍保留定义 | feature_decisions.csv；当前字典business_protected |
| 目标编码、标准化与稀疏预嵌入 | 已完成：用户分组OOF高维类目编码、训练尺度及8维类别投影 | preprocessing.json；docs/stage2_preprocessing.md |
| 训练期拟合防泄漏 | 已完成并注明边界：筛选/填充/编码/缩放/分解仅训练拟合；验证选择先冻结 | preprocessing.json；audit.json；编码边界测试 |
| 分组基线和消融 | 已完成：第一轮6组LR，补充6个新模型及2个冻结参考；人群与覆盖分别评价 | 两轮experiments.json；encoding_metrics.csv |
| 低覆盖效果支持 | 已有评估机制；低活跃及新近观测共现覆盖内训练正例不足，不能确认增量效果 | training_group_diagnostics.json；综合报告D04 |
| 冻结特征数据集 | 已完成：四截点CSR矩阵、三键侧表和全量重放 | preprocessing.json；data/catalog/stage2_complete_v1.json |

## 2.4 多维度探索性数据分析

| 验收点 | 状态与实现 | 证据位置 |
|---|---|---|
| 基础行为和时间 | 核心完成：四行为、日活/周活、小时、工作日/周末 | figures/eda_*；eda_baseline.json；SQL摘要 |
| 漏斗、分群和商品类目 | 核心完成：成熟严格路径、RF代理、转化周期及跨日期复购代理 | figures/；tables/；supplementary_eda.json |
| 可视化与洞察 | 已完成：10类核心EDA及10幅分组评价图，附分母和边界 | figures/；README.md |
| 联动、下钻和导出 | 已完成：日期×人群×类目全局重算、商品下钻及CSV | docs/eda_dashboard1.md；eda_audit.json |
| 展示细项 | 待补：人均行为/购买记录卡、类目覆盖定义、周末标记、商品类目列、漏斗各级比率及分母 | 综合报告D02；src/user_behavior_analysis/assets/eda/ |
| 节假日对比 | 数据条件不具备：观察期无法定节假日，不构造虚假对照 | docs/business_conventions.md |

## 全阶段工程与数据边界

原始有效记录保留，每用户每小时>90条只标记；原始次数与不同四元组次数分别统计。
没有金额采用RF/购买记录次数代理，不称完整金额RFM；没有曝光不称真实CTR。
没有订单/数量时不称真实订单或购买件数；没有分钟秒只确认跨小时顺序；没有真实会话不推算在线时长。
目标编码内部为用户分组OOF，最早推理不早于训练标签成熟，时间外评价另执行。
工程规范、函数注释、类型、测试和分支CI贯穿各阶段。历史执行证据保留其基线日期和提交。
第三阶段正式多模型、采样比较、深度模型、融合和模型看板不计作第二阶段已完成成果。
