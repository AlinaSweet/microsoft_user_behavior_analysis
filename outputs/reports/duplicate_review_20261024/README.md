# 重复值材料归档与复核

日期：2026-10-24。用户提供的说明、Excel、CSV和三张图按内容原样归档，文件名映射及SHA-256见 data/catalog/duplicate_review_20261024.json。Office临时锁文件未归档；客户小时明细压缩包保存在本地data/interim，未提交Git。

独立核验状态：passed，见 verification.json。重新从原始CSV分块构建新的全局SQLite四元组关系，对附件682,940个用户小时的全部10项指标逐值比较，均一致；重复次数分布和四种行为影响计数一致。未用旧去重表代替原始输入。

## 关键结果

| 指标 | 数值 |
|---|---:|
| 原始记录 | 12,256,906 |
| 不同四元组 | 6,213,379 |
| 按四元组保留一条会合并的记录 | 6,043,527 |
| 活跃用户小时 | 682,940 |
| 恰好90条的用户小时 | 494 |
| 超过90条的用户小时 | 15,428 |
| 超线时段涉及记录 | 1,956,008 |
| 超线时段涉及用户 | 3,357 |
| F(90) | 97.7409% |

以上“会合并的记录”不是已确认的错误日志。超过90条只标记，不删除、不截断。当前已按用户确认登记[分析策略](../../../docs/duplicate_policy.md)。

## 内容

- analysis_notes.md：用户原始说明，保留其来源路径记载和方法。
- user_hour_distribution.xlsx：用户提供的分布、重复情况与行为影响工作簿。
- user_hour_bins.csv / user_hour_exact.csv：原始分箱、逐次数分布。
- key_occurrences.csv / behavior_dedup_impact.csv：原始四元组分布及行为影响。
- 三张PNG：用户提供的图表。
- high_frequency_user_hours.csv：由用户全量明细派生的15,428条待核查清单，补齐高频用户小时的单独清单。
- verification.json：本次独立全量核验。
- 90条参考线的计算与边界以核验结果和 docs/duplicate_policy.md 为准；原始分箱CSV没有拆分51–90与91–100，不改写原附件。

## 高频清单字段

user_id：文本客户标识；event_time：源小时；raw_record_count：全部记录数；
distinct_item_behavior_count：不同商品行为组合数；extra_same_key_records：相同四元组的额外记录量；
max_key_occurrences：单四元组最大出现次数；distinct_items：商品数；behavior_type_count：行为类型数；
pv_count/fav_count/cart_count/buy_count：四类行为记录数；review_status：pending_review。

## 下一步

数据库保留全部有效记录与四元组对照，支持后续比较用户活跃、商品热度和购买特征。当前没有证据把全部同小时相同字段记录认定为采集错误。
