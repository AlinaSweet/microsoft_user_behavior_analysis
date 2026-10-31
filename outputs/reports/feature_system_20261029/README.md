# 全维度特征体系交付

实际构建完成：2026-10-30。目录日期为任务启动日期20261029。

## 交付入口

- [Excel特征字典](feature_dictionary.xlsx)：汇总、445条定义、中间表依赖与字段质量。
- [可搜索特征字典](feature_dictionary.html)。
- [特征方法与复现](../../../docs/feature_system.md)。
- [中间表结构与依赖](../../../docs/intermediate_table_design.md)。
- [深入EDA报告](../eda_extension_20261029/README.md)与[离线页面](../eda_extension_20261029/dashboard.html)。

## 实际产出

- 完整有效记录12,256,906条，四元组键6,213,379个，原始次数完整保留。
- 8类标准事实/键表/聚合表，用户小时与既有数据库682,940×10项逐值一致。
- 439个标量字段（含32个SVD坐标）与6类逻辑序列输入，字典共445项。
- 4个历史截点，4,426,649行候选特征快照；每截点16个分片。
- 训练期冻结SVD、IDF、词表与788商品共现图；13,806条规则。
- 4份逐列质量和时间/计数控制记录；标签独立保存。

## 本目录文件作用

| 文件 | 作用 |
|---|---|
| summary.json | 实际字段数、分组、截点行数及标签成熟度 |
| feature_dictionary.json | 可供程序读取的445条定义及最新质量 |
| ../../../docs/feature_dictionary.md | 完整逐条Markdown字典 |
| feature_dictionary.html / .xlsx | 可搜索和Excel两种阅读入口 |
| quality_profiles.json | 四截点共1756条全量标量字段质量画像 |
| base_rebuild.json | 完整记录基表重建与计数/逐值核对证据 |
| latent_fit.json | 冻结SVD和共现图的训练维度、参数、方差与规则数 |
| snapshot_2025-11-25.json | 第一个截点的字段、行数、边界、文件指纹 |
| snapshot_2025-12-02.json | 第二个截点的同类证据 |
| snapshot_2025-12-09.json | 第三个截点的同类证据 |
| snapshot_2025-12-19.json | 最新截点的同类证据，未来标签不可用 |
| delivery_audit.json | 交付数据、指纹、数组与Excel一致性复核 |
| run_record.json | 完成时间、交付源码指纹、依赖、资源、SVD参数与执行边界 |
| static_checks.json / static_checks.log | 本轮代码静态检查，区别于历史测试 |

大表、序列、NPZ、冻结模型和DuckDB缓存仅本地；本目录报告、字典、小表和图表可纳入Git。
当前数据入口：[current_datasets.json](../../../data/catalog/current_datasets.json)。

439个候选标量已产出，正式筛选尚未执行。SVD方差0.2587%、最新可用候选对23.02%、共现范围有限等限制见方法文档。
2026-10-31补充：新增23项边界测试，完整102项测试、第一阶段全量回归及独立计数/标签重算通过。
[最新交付复核](../delivery_review_20261031/README.md)记录当前状态，远程Quality另有实际检查点。
按用户原模板五列另交付[特征拆分整理表](feature_split.xlsx)。

2026-10-31经本机HTTP实际打开基础EDA、深入EDA和字典页面；主要切换/搜索/展开功能正常。
图表与Excel已直接渲染核对；任意日期、人群、类目全局联动仍未实现。
