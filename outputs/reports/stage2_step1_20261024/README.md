# 第二阶段第1项：SQLite与SQL分析

日期：2026-10-24。全量数据库构建、11项SQL执行及计数控制通过。

## 当前输入与数据

全部12,256,906条有效原记录进入behaviors主表，不以业务四元组唯一约束丢弃记录。
10,000用户、2,876,947商品、8,916类目、744小时、31天。
数据库约3.78GiB，保留本地，清单为data/catalog/analysis_raw_v1.json。

用户小时共682,940，四元组共6,213,379。
超过90条的15,428个用户小时涉及1,956,008条记录和3,357名用户，
标记pending_review，记录全部保留。旧clean_v1/base_v1继续作为历史对照。

## 交付与验证

- sql/schema.sql、indexes.sql、diagnostics.sql和queries目录：规范基础表、索引、对照及SQL。
- SQLiteClient：只读参数化查询，支持小表DataFrame和大结果流式读取。
- database.json：每批10万条，全量六列规范值指纹相同；源清单未变、外键和完整性检查通过。
- database_audit.json：682,940个用户小时的10项指标逐值比对原始CSV独立参考结果，全部一致。
- sql_analysis.json：全部查询的SQL/结果指纹、行数、预览、耗时和控制指标。
- quality.json：79项测试及全部格式、类型、pylint检查通过。
- 第一阶段接入后完整回归在 ../stage1_review_20261024_04/audit.json，状态passed。

核心第三范式表与派生分析表分开说明，详见 ../../../docs/sqlite_analysis.md。
源记录序号不代表真实同小时顺序；小时序列不构造并列行为先后。
分群SQL是购买/高频交叉人群，完整RFM代理特征在第二阶段第2项实现。
严格漏斗和复购代理使用完整7日随访；不能解释为真实订单、金额或CTR。

## 完整查询输出

| 查询 | 输出行数 | 秒 |
|---|---:|---:|
| overview | 1 | 32.9833 |
| behavior_distribution | 4 | 1.6554 |
| daily_active | 31 | 2.0185 |
| weekly_active | 31 | 0.6639 |
| popular_items | 50 | 27.4241 |
| popular_categories | 50 | 27.3161 |
| user_sequences | 682940 | 2.2511 |
| funnel_reach | 4 | 9.4092 |
| strict_funnel | 1 | 22.4036 |
| user_proxy_segments | 4 | 0.5913 |
| item_repurchase | 92753 | 0.7025 |

完整CSV保存到data/processed/analysis_raw_v1/sql_results，原始导出未按20行预览截断。
热门商品/类目按脚本规则取Top50。summaries目录另保存适合Git的小型完整结果。
item_repurchase及user_sequences完整数据保留在本地。

## 下一项

第二阶段第2项：生命周期、序列、SVD、共现关联、偏好与RF/购买次数代理特征。
此后才进行目标编码、未来7天用户购买预评估和完整EDA，台账未登记为完成。

本轮由Codex进行代码与内容复核；GitHub分支与CI在交付记录单独核验。
构建报告的code_commit为启动时HEAD，实际实现文件指纹已另登记到数据清单。
