# 第一二阶段完成与复核报告

微软商城用户行为分析｜2026年11月15日

复核实现提交：`62fc30a93c60b78840d52a8fa0df1884beb743c4`。

## 复核结论

第一阶段四项工作已在实际提供的数据规模下完成。第二阶段的数据库、源特征与预拼接、训练期预处理和固定模型预实验、多维EDA等核心成果均已落地，本轮数值与工程复核通过。严格逐条对照原大纲和导师截图，跨截点特征稳定性专项和看板一若干展示细项仍待补齐，因此不将全部细项笼统写成百分之百完成。

本次复核基于提交62fc30a，重新执行第一阶段完整审计、四截点标签重算、全部矩阵与保存预测重放、数据库与聚合对照、EDA组合筛选核对，并检查当前文件指纹和远程CI。没有重新训练或调整模型，也没有改写原始数据和既有数值成果。

| 任务 | 状态 | 当前成果 |
| --- | --- | --- |
| 第一阶段一 工程环境与版本管理 | 已完成 | Python环境、资源调度、分层目录、规范与三级Git流程已建立。 |
| 第一阶段二 文献与技术栈 | 已完成 | 5篇论文、数字平台案例及工具和实验方案齐全。 |
| 第一阶段三 加载清洗与质量 | 现有规模完成 | 12,256,906条数据全量处理通过；未进行亿级实测。 |
| 第一阶段四 Parquet与中间表 | 已完成 | 类型压缩、格式转换和三维聚合均有真实产物。 |
| 第二阶段一 SQLite与SQL | 已完成 | 规范化表、索引、11项SQL和Python接口通过。 |
| 第二阶段二 特征与预拼接 | 已完成 | 439标量、6类序列和4截点宽表；代理边界已明确。 |
| 第二阶段三 预处理与有效性 | 主体完成 | 训练期分组筛选、变换和预实验完成；跨截点专项稳定性表待补。 |
| 第二阶段四 EDA与看板一 | 核心完成 | 全局联动与核心探索通过；若干原大纲展示细节待补。 |

实际数据为12,256,906条记录、10,000名用户、2,876,947个商品和8,916个类目，覆盖2025年11月18日至12月18日。大纲描述的百万用户和亿级场景不是本项目当前数据的实测规模。

## 第一阶段四项完成情况

### 工程环境与版本管理

已配置Pandas、Dask、NumPy、PyArrow及固定依赖，按api、service、dao、models、common分层。真实Dask worker、内存限制与分块读取检查通过；main、dev、feature三级流程、提交规范和自动CI可用。大型数据保留本地并通过清单记录，代码和小型结果同步GitHub。

核对位置：E03；configs/dask.yaml；requirements*.txt；.githooks；.github/workflows/quality.yml。

### 文献与技术方案

5篇经典论文的核心思想、证据与适用边界已记录，另有数字平台案例、Spark与Dask比较、特征方案和实验计划。论文中的效果数值属于原论文，不冒充本项目训练结果；没有将理论比较登记为Spark与Dask的同机实测速率对比。

核对位置：E04；docs/research/references.json；docs/research/tech_stack_comparison.md。

### 全量加载清洗与质量管控

已对全部12,256,906条记录执行结构、标识、行为和小时级时间校验，并保留IQR和3σ异常诊断。当前政策为保留全部有效记录，每用户每小时超过90条只标记；不同四元组数6,213,379用于另一计数口径。同小时相同字段不足以证明错误采集，不能直接删除。

核对位置：E05；data/catalog/validated_records_v1.json；本轮第一阶段和标签独立审计。

### 压缩格式与基础中间表

已执行字段类型压缩、Parquet转换和用户、商品、时间维度聚合。历史归并事件压缩从161.61MiB降至77.20MiB，属于原测量；当前全记录基表base_raw_v2另行保存原始次数。旧clean_v1/events与base_v1保留作历史对照，当前特征不读取其归并事件。

核对位置：E06；data/catalog/base_v1.json；data/catalog/base_raw_v2.json。

阶段边界：分块和并行方案在现有约1,225万条数据上已验证；尚未执行一亿条以上的压力测试。最终错误日志删除规则仍需真实事件标识或采集证据，当前按已确认保留策略交付。

## 第二阶段四项完成情况

### 数据库与SQL

SQLite保存全部有效记录，事实表和维表、索引、批量导入及Pandas交互接口齐全。11项SQL覆盖总量、行为分布、日活、滚动周活、热门商品类目、小时序列、漏斗、分群和复购代理。完整导出保留本地，Git中的预览不冒充全量结果。

核对位置：E07；sql/queries；src/user_behavior_analysis/dao/sqlite_client.py。

### 全维度特征与预拼接

439个标量和6类逻辑序列覆盖用户、商品、类目、交互、时间、生命周期、RF代理、漏斗、序列、SVD与共现。用户商品主宽表已提前拼接；四截点三键唯一、匹配与439列源值已有全量审计，本轮确认其指纹未变。

核对位置：E08、E09、E12；data/catalog/prejoined_wide_v1.json。

### 特征预处理和有效性验证

训练期画像后保留207个标量，分组为基础80、业务64、序列22、SVD36、共现5。高维偏好类目采用用户分组OOF目标编码，低维类别用训练词表，另有8维稀疏预嵌入；最终259列矩阵。第一轮6组LR和补充轮6个新模型均有完整样本评价。跨截点同一套特征稳定性专项仍待补齐。

核对位置：E10至E14；本轮stage2_replay/audit.json。

### 探索分析与看板一

已实现日期、人群、类目全局重算、商品下钻和CSV，覆盖四行为、时段、日趋势、活跃长尾、商品类目、成熟路径和未来关联。当前有10类核心静态EDA图及10幅分组MI/相关性图，补充RF分群、转化周期、复购和覆盖统计。部分指标卡与展示标注仍待补齐。

核对位置：E15至E18；outputs/reports/stage2/figures及tables。

| 截点 | 候选行 | 正例 | 标签状态 |
| --- | --- | --- | --- |
| 2025-11-25 | 1,030,893 | 2,735 | 训练 成熟 |
| 2025-12-02 | 1,061,515 | 2,525 | 验证 成熟 |
| 2025-12-09 | 1,117,324 | 5,175 | 测试 成熟 |
| 2025-12-19 | 1,216,917 | 不适用 | NULL 未成熟 |

## 导师截图要求逐项复核

复核对象为对话中10月29日、11月6日和11月13日提供的截图。结论以当前实现、实际数据文件和可追溯证据为准。已完成表示对应动作和产物存在；数据支持不足表示不能估计效果，不等于已证明无效；部分完成的细项保留明确待办。

| 截图日期与要求 | 结论 | 实际落实及证据 |
| --- | --- | --- |
| 10月29日 参考看板一补充EDA | 已完成核心内容 | 全量四模块探索、联动、下钻和CSV均已实现；展示细项见待办D02。 E15、E17；EDA独立核对 |
| 10月29日 提供中间表与特征整理文档 | 已完成 | 源表、粒度、公式、处理、缺失及筛选状态可查，445源定义与9表示分列。 E08、E12；docs/intermediate_table_design.md |
| 10月29日 区分计算汇总表与特征中间表 | 已完成 | 频数/聚合表、实体特征表、预拼接层、标签、矩阵分别登记，不混用旧归并口径。 E05、E20；docs/repository_map.md |
| 11月6日 预先拼接用户商品类目特征 | 已完成 | 4,426,649行已预拼接，三键和439列源值审计通过；本轮指纹未变。 E09；本轮fingerprints.json |
| 11月6日 先缺失常量方差再筛相关性互信息 | 已完成 | 全部训练候选画像后分组筛选，207标量保留，232本轮排除；规则冻结。 E10；configs/feature_validation.json |
| 11月6日 SVD和共现低覆盖单独评估 | 已完成评估机制 | 单列覆盖、条件统计和未知回退；低支持人群明确标为不可估计，不宣称有效。 E11、E14；覆盖内相关性图 |
| 11月6日 分截点和用户群观察特征差异 | 部分完成 | 训练期分群MI、跨截点分群效果与覆盖已有；尚无同一套特征的完整跨截点MI/相关性稳定性专项表。 E11、E13、E14、E16；待办D01 |
| 11月6日 保留漏斗和RF业务特征 | 已完成 | 40个非恒定RF/漏斗字段按业务保护；常量只退出当前训练，不删字典定义。 E10、E12 |
| 11月6日 用简单逻辑回归做消融 | 已完成 | 第一轮6组完整样本LR；补充轮6个新模型并列2个既有参考。 E13、E14；本轮概率重放 |
| 11月13日 用户商品对未来7天标签单独落地 | 已完成 | 3,209,732条成熟候选都有0/1；1,216,917条未成熟候选保持NULL。 本轮pair_labels.json；pair_targets_v1 |
| 11月13日 标签按截点用户商品三键对齐 | 已完成 | 与宽表严格三键连接，原事件独立重算差异0；用户级标签独立。 E09；本轮pair_labels.json |
| 11月13日 分组基线后逐组增加高级特征 | 已完成 | 基础、业务、序列、SVD、共现分别评估；同轮对照采用相同样本和固定设置。 E13、E14 |
| 11月13日 全部拟合只用训练集 | 已完成并有边界 | 筛选、填充、缩放、词表、目标编码、投影只训练拟合；用户OOF与成熟时间约束单列。 E10、E14；target_encoding.py边界测试 |

### 粒度与泄漏要求的关键确认

主监督样本的一个观测是一个截点下的一个用户商品对；正例只表示该用户随后7天购买同一商品。用户购买其他商品只进入独立用户级探索，不能作为该候选商品正例。12月19日缺少随后7天观测，全部标签保持NULL，不能当作负例。

目标编码内部采用按用户划分的5折交叉拟合，排除本人所在折的类别统计和先验；它不等于时间折外编码。训练标签在12月2日成熟，因此编码最早也在该时点可用于推理。验证与测试只应用冻结规则，不参与映射、填充、缩放、投影或筛选拟合。

### 低覆盖特征的结论边界

| 训练人群 | 候选行与正例 | 覆盖内共现行与正例 | 可作出的判断 |
| --- | --- | --- | --- |
| 低活跃 | 3,872行 19正例 | 171行 0正例 | 共现MI支持不足 |
| 高活跃 | 969,408行 2,524正例 | 21,894行 39正例 | 可估计但需谨慎 |
| 新近观测 | 12,838行 55正例 | 259行 0正例 | 共现MI支持不足 |

新近观测是源数据中首次出现时间的代理，不代表实际注册或完全无历史的新用户。SVD与共现的覆盖随截点降低，已分别报告并设置回退；保留评估机制不能替代对每个人群有效性的实证。

## 本轮复核结果与实验解读

| 检查 | 覆盖范围 | 本轮结果 |
| --- | --- | --- |
| 代码与真实环境 | 规范 格式 类型 静态分析 157项测试 Dask worker | 通过 |
| 当前文件指纹 | 774个去重后的在用数据 代码 报告记录 | 全部一致 无在用文件缺失 |
| 独立对级标签 | 4截点 4,426,649行 对照未聚合原事件 | 三键及标签差异0 |
| 全部处理后矩阵 | 4,426,649行 259列 | 逐值重放最大差异0 |
| 新模型保存预测 | 验证和测试共2,178,839行 6组新模型 | 系数重放最大差异0 |
| 目标编码映射 | 6套映射 8,177个类别条目 | 独立训练分组核对差异0 |
| SQLite与聚合 | 682,940个用户小时 10项指标及4截点关键计数 | 完整性 外键 逐值对照通过 |
| EDA全局筛选 | 全窗口 组合筛选 单日 成熟截点 空结果 | 与原事件核对差异0 |
| 远程实现状态 | main dev feature/stage2-complete 的62fc30a | 三分支Quality均通过 |

774是本轮扩大到源代码、标签、矩阵和报告依赖后的唯一文件记录数；先前513的检查范围较小，两者不能直接当作质量变化。归档后的历史第一阶段审计引用已按归档清单找到原文件并核对SHA，属于历史追溯，不是当前运行缺文件。

| 输入组 | 验证AUC | 验证AP | 测试AUC | 测试AP |
| --- | --- | --- | --- | --- |
| business | 0.85608 | 0.02955 | 0.83638 | 0.03946 |
| te_business | 0.85591 | 0.02943 | 0.83572 | 0.03985 |
| te_sequence | 0.85324 | 0.02977 | 0.83424 | 0.03975 |
| te_svd | 0.85733 | 0.02926 | 0.83667 | 0.03962 |
| te_preembedding | 0.85517 | 0.02948 | 0.83614 | 0.03989 |

表内business为既有独热编码参考，te_*为本轮编码模型。同轮比较才能区分高级特征增量和编码差异。8组声明对照按验证AP选出te_sequence；上一轮独热序列组的验证AP约0.02988，仍略高于本轮目标编码序列组约0.02977。目标编码降低维度，但不能宣称全面提高预测效果。测试结果没有用于继续调参。

## 尚需补齐的事项与数据边界

| 编号与事项 | 状态 | 需要补充什么 |
| --- | --- | --- |
| D01 跨截点特征稳定性证据 | 专项待补 | 冻结当前特征清单，按成熟截点和用户群列同口径分布/相关性/覆盖；标签相关诊断仅作评估，不回流测试标签调筛选。 |
| D02 看板一展示细项 | 展示待补 | 单列人均行为/购买记录卡；明确品类覆盖定义；每日趋势标周末；热门商品显示已有类目字段；漏斗补各级比率和分母。 |
| D03 亿级压力验证 | 尚未执行 | 在真实更大数据或明确标注的合成压力集上测峰值内存、溢写与吞吐，说明机器和配置。 |
| D04 罕见人群高级特征有效性 | 数据支持不足 | 低活跃及新近观测人群的覆盖内共现训练样本均无正例；保留不可估计标记，后续扩大历史/样本再验证。 |

D01判断：补充后才能把11月6日该细项记为完全落实。

D02判断：已有后台数据可支持，多数属于展示和指标说明，不改变现有数值验收结果。

D03判断：目前只可声称提供的1,225万条数据规模已验证。

D04判断：不是程序失败，也不能当作高级特征已经对这些人群有效。

### 已明确的数据边界

金额、单价、订单和数量缺失，使用已获确认的RF和购买记录次数代理；不解释为完整金额RFM、真实订单量或购买件数。曝光缺失时分析浏览量与购买覆盖，不称真实CTR。

源时间只到小时，同小时行为不能还原先后；严格路径只认跨小时顺序。同一小时可能有多种行为，因此转移是多标签，行和可以超过100%。观测活跃小时桶也不是在线时长，不能据此构造会话退出率。

项目日历在本数据窗口内没有法定节假日观测，无法完成节假日与非节假日实证对照；31天历史也不能支持长期流失、长期价值或多季节稳定性。

过去7天有交互的候选仅覆盖未来实际购买组合约11.87%至16.39%。候选内AUC和AP只评价这一范围，不能直接视为全站推荐收益。已有EDA观察过这些日期，当前属于历史回测而非从未接触的未来盲测。

第三阶段的约7比2比1随机对照、SMOTE与欠采样和权重方案、XGBoost与LightGBM及调参、深度模型、融合、解释与模拟A/B仍未执行。本报告不将固定LR预实验记作第三阶段全面完成。

## 成果目录与复核证据

项目根目录为/Users/alina/Desktop/实习/Github。下表位置均相对该目录。大型Parquet、SQLite、标签、矩阵和模型保留在data/processed，Git同步代码、配置、说明、字典和数据清单。

| 用途 | 对应位置 |
| --- | --- |
| 当前总入口 | README.md；docs/repository_map.md；docs/file_inventory.csv |
| 第一阶段1和2 | docs/stage1_completion.md；docs/research/ |
| 第一阶段3和4 | docs/cleaning_rules.md；docs/preprocessing_rules.md；outputs/reports/stage1_step3及stage1_step4 |
| 第二阶段1 | docs/sqlite_analysis.md；sql/；outputs/reports/stage2_step1_20261024/ |
| 第二阶段2 | docs/feature_system.md；docs/prejoined_features.md；data/catalog/features_raw_v2.json及prejoined_wide_v1.json |
| 第二阶段3 | docs/feature_validation.md；docs/stage2_preprocessing.md；outputs/reports/stage2/ |
| 当前特征字典 | outputs/reports/stage2/feature_dictionary.xlsx；同名json及html |
| 第二阶段4 | docs/eda_dashboard1.md；outputs/reports/stage2/figures及tables；scripts/run_eda_dashboard.sh |
| 数据实际入口 | data/catalog/current_datasets.json；stage2_complete_v1.json |
| 本轮新复核 | outputs/reports/stage1_stage2_review_20261114_01/ |

### 本轮证据文件

第一阶段：stage1/audit.json及其quality、environment、preprocessing证据。第二阶段：fingerprints.json、pair_labels.json、stage2_replay/audit.json、independent_data_audit.json、eda/eda_audit.json和stage2_audit.json。路径均相对本轮新复核目录。远程核对保存在cloud_snapshot.json。

### 原始要求与主要方法来源

- E01 [原始项目大纲](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/requirements/project_brief.pdf)：`docs/requirements/project_brief.pdf`。
- E02 [看板一和通用展示要求](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/requirements/dashboard_outline.pdf)：`docs/requirements/dashboard_outline.pdf`。
- E03 [第一阶段工程及研究文档](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/stage1_completion.md)：`docs/stage1_completion.md`。
- E04 [五篇论文与技术方案](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/research/README.md)：`docs/research/README.md`。
- E05 [当前重复值政策](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/duplicate_policy.md)：`docs/duplicate_policy.md`。
- E06 [第一阶段清洗与压缩测量](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/stage1_step4/preprocessing.json)：`outputs/reports/stage1_step4/preprocessing.json`。
- E07 [数据库与SQL验收](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/stage2_step1_20261024/README.md)：`outputs/reports/stage2_step1_20261024/README.md`。
- E08 [源特征方法和实际数据版本](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/feature_system.md)：`docs/feature_system.md`。
- E09 [预拼接全量审计](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/prejoined_wide_20261107/audit.json)：`outputs/reports/prejoined_wide_20261107/audit.json`。
- E10 [训练期筛选及六组原实验](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/feature_validation_20261114/selection.json)：`outputs/reports/feature_validation_20261114/selection.json`。
- E11 [分人群和高级组覆盖诊断](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/feature_validation_20261114/training_group_diagnostics.json)：`outputs/reports/feature_validation_20261114/training_group_diagnostics.json`。
- E12 [当前字典及全部预处理方法](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/stage2/feature_dictionary.json)：`outputs/reports/stage2/feature_dictionary.json`。
- E13 [原六组逻辑回归结果](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/feature_validation_20261114/experiments.json)：`outputs/reports/feature_validation_20261114/experiments.json`。
- E14 [目标编码及预嵌入对照](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/stage2/encoding_experiments.json)：`outputs/reports/stage2/encoding_experiments.json`。
- E15 [当前看板使用和指标口径](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/eda_dashboard1.md)：`docs/eda_dashboard1.md`。
- E16 [跨截点分群及覆盖补充证据](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/outputs/reports/stage2/supplementary_eda.json)：`outputs/reports/stage2/supplementary_eda.json`。
- E17 [看板页面实际渲染逻辑](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/src/user_behavior_analysis/assets/eda/dashboard.js)：`src/user_behavior_analysis/assets/eda/dashboard.js`。
- E18 [类别排名与筛选后端逻辑](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/src/user_behavior_analysis/service/interactive_eda.py)：`src/user_behavior_analysis/service/interactive_eda.py`。
- E19 [旧报告可恢复清单](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/docs/archive_manifest.json)：`docs/archive_manifest.json`。
- E20 [当前数据依赖入口](https://github.com/AlinaSweet/microsoft_user_behavior_analysis/blob/62fc30a93c60b78840d52a8fa0df1884beb743c4/data/catalog/current_datasets.json)：`data/catalog/current_datasets.json`。
