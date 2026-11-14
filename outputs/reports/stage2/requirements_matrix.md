# 第二阶段逐项验收

依据[原始项目大纲](../../../docs/requirements/project_brief.pdf)、[双看板大纲的看板一](../../../docs/requirements/dashboard_outline.pdf)，
以及用户提供的导师截图（10月29日、11月6日、11月13日）和已确认的数据口径。日期：2026-11-14。

| 来源/任务 | 已落实的行为 | 可核对的文件 |
|---|---|---|
| s2_01数据库与Python接口 | 全部有效原记录、规范化维表、索引、批量与分块读取 | docs/sqlite_analysis.md；stage2_step1_20261024/database*.json；src/.../dao/sqlite_client.py |
| s2_01基础/复杂SQL | 11项全量查询、窗口/子查询及Python结果复核 | sql/queries/；stage2_step1_20261024/sql_analysis.json |
| s2_02用户/商品/时间/交互统计 | 1/3/7/30天窗口，439标量完整源定义 | feature_dictionary.json；data/catalog/features_raw_v2.json |
| s2_02RF、漏斗、转移、衰减 | 明确金额/小时边界的代理；多路径与并列掩码 | docs/feature_system.md；原字典及各snapshot质量 |
| s2_02高级特征/序列 | 冻结交互SVD、共现与6类序列及PAD/UNK | data/processed/features_raw_v2/latent及snapshots；源catalog指纹 |
| s2_03异常、缺失、常量、方差 | 全训练画像、低覆盖单列、训练填充与缺失指示 | feature_validation_20261114/selection.json、training_group_diagnostics.json |
| s2_03编码、标准化 | 高维偏好类目用户OOF Target Encoding，低维独热、训练尺度 | preprocessing.json；docs/stage2_preprocessing.md |
| s2_03稀疏预嵌入 | 三类训练类别8维稀疏投影，未知桶/覆盖管理与冻结参数 | preprocessing.json；data/processed/stage2_complete_v1/transform.joblib |
| s2_03互信息与相关性 | 各组排名、状态与完整所选数值Spearman矩阵；5组分别出图 | importance_rank.csv、selected_correlations.csv、figures/mi_*及correlation_* |
| s2_03评价与处理后数据 | 原六组LR＋8组编码对照、全部四截点CSR及三键侧表 | encoding_experiments.json、encoding_metrics.csv、audit.json |
| s2_04至少8类图/洞察 | 10类核心EDA＋10幅分组筛选图，补充深度统计 | figures/；tables/；README.md |
| 看板一四模块 | 全局日期×人群×类目，商品下钻、两种排名、CSV | docs/eda_dashboard1.md；src/.../assets/eda；eda_audit.json |
| 导师：先EDA再设计中间表 | 已形成全量探索证据及分层结果，再登记正式宽表与筛选 | tables/；docs/intermediate_table_design.md；prejoined_wide_20261107审计 |
| 导师：特征整理和数量 | 445源定义全量保留，207入选，9表示与259矩阵列单列 | feature_dictionary.xlsx、JSON与HTML |
| 导师：提前预拼接三类核心特征 | 4,426,649行，三键唯一、LEFT JOIN匹配、439列逐值控制 | data/catalog/prejoined_wide_v1.json；prejoined_wide_20261107/audit.json |
| 导师：用户商品粒度未来7天标签 | 稠密候选逐行0/1，按截点/用户/商品严格连接；未成熟NULL | feature_validation_20261114/samples.json、audit.json；pair_targets_v1 |
| 导师：用户级标签不混用 | 用户级补充EDA单独接口与分母；对级主任务独立 | eda_mature_example.json；interactive_forward.py |
| 导师：分组而非400列混跑 | 基础/业务/序列/SVD/共现分组；高级覆盖内外及回退 | selection.json；encoding_experiments.json；原experiments.json |
| 导师：低活跃/高活跃/冷启动 | 训练分群诊断，验证/测试分群表现；新近观测非注册 | training_group_diagnostics.json；两轮experiments.json |
| 导师：业务逻辑保护 | 40个非恒定RF/漏斗字段保留；常量仍说明不可学习 | feature_decisions.csv；当前字典business_protected |
| 导师：消融预实验 | 固定LR逐组增量，验证选择先冻结，再看测试 | encoding_validation_choice.json；原frozen_validation_choice.json |
| 导师：仅训练拟合防泄漏 | 所有筛选/填充/编码/缩放/分解训练拟合，验证测试transform | preprocessing.json；全量重放audit.json；边界测试 |
| 用户：不按同小时重复删行为 | 全有效记录保留、>90只标记，原始与四元组双计数 | docs/duplicate_policy.md；eda_audit.json；base_raw_v2清单 |
| 代码规范与工程管理 | 每个自定义函数Google注释、类型、规范、测试、分支CI | AGENTS.md；stage1/quality.json；cloud_delivery.json |

## 数据限制下的验收边界

没有金额时采用已获用户接受的RF/购买次数代理，不称完整金额RFM；没有曝光时用浏览覆盖，不称CTR。
没有订单/数量时统计购买日志和组合，不称真实订单或购买件数；没有分钟秒时只确认跨小时顺序。
没有真实会话和在线时长，用观测活跃小时及转移间隔。31天内无法定节假日，节日实证对照不具备数据条件。
这些是经说明的数据边界，不以虚构指标填满大纲。
目标编码内部为用户OOF，时间外评价另执行；最早推理时间不早于训练标签成熟，不能冒称更早时间折外编码。
第三阶段多模型、SMOTE/欠采样/权重对照、深度学习和第二看板不计作第二阶段已完成内容。
