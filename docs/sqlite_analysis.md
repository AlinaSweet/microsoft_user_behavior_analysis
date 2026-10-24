# 第二阶段第1项：保留原记录的SQLite与SQL分析

本轮口径已于2026-10-24经用户确认。数据库以validated_records_v1为输入，
保留全部有效源记录；90条参考线只标记，不删除、不截断。原始CSV和历史v1结果保留。

## 运行与复现

在仓库根目录运行：

    bash scripts/run_project.sh database

默认输入data/catalog/validated_records_v1.json；
输出data/processed/analysis_raw_v1/behavior.sqlite；
报告outputs/reports/stage2_step1_20261024/database.json。

数据库和构建文件存在时拒绝覆盖。重新运行应使用新数据库路径与报告目录，例如：

    bash scripts/run_project.sh database \
      --database data/processed/analysis_raw_v2/behavior.sqlite \
      --report-dir outputs/reports/stage2_step1_v2

全量执行11项SQL并流式导出：

    PYTHONPATH=src .venv/bin/python scripts/run_sql_analysis.py

完整查询结果留在data/processed/analysis_raw_v1/sql_results，
小型摘要、SQL指纹和计数控制保存到阶段报告。预览只取20行，不能当作完整导出。
热门商品/类目查询按脚本声明取Top50，其余查询不以预览截断结果。

## 核心表与第三范式

- users：用户ID登记，不编造注册时间、画像。
- categories、items：商品到类目的关系只保存一次；导入时全局检查类目一致性。
- calendar_dates、event_times：日期、源小时关系；星期等可推导属性置于视图。
- behavior_types：行为编码字典。
- behaviors：一行代表一个有效源记录，以event_id为主键，业务四元组允许重复。
- dataset_metadata：输入清单、指纹、策略和生成信息。
- canonical_events：关联商品类目后恢复原六列的视图。

函数依赖：event_id决定用户、商品、行为、小时；item_id决定类目；
event_time决定日期。类目和日历派生属性不重复写入行为事实表。
user_hour_stats为明确标识的分析聚合表，不把该派生表宣称为基础第三范式关系。

## 重复与高频分析

key_occurrences按用户、商品、行为、小时分组，保存出现次数及最小源记录序号。
此视图用于对照，不修改behaviors。

user_hour_stats同时记录原始条数、四元组数、额外同键记录量、最大出现次数、
不同商品数、行为类型数及四种行为次数。
high_frequency_user_hours从元数据读取90阈值，以严格大于判定，并给出pending_review。

## 查询口径

| SQL | 用途 |
|---|---|
| overview | 全量记录、用户、商品、类目及时间边界 |
| behavior_distribution | 四类原始行为数量与占比 |
| daily_active | 自然日去重活跃用户 |
| weekly_active | 连续7个自然日的不同活跃用户，首6日标覆盖不足 |
| popular_items / popular_categories | 按脚本排序的Top50商品/类目 |
| user_sequences | 有记录小时桶序列及相邻小时差；同小时不构造先后 |
| funnel_reach | 行为覆盖，不能解释为严格转化路径 |
| strict_funnel | 同用户商品、严格跨小时pv→cart→fav→buy，完整7日随访 |
| user_proxy_segments | 是否观测到购买与是否涉及高频小时的交叉人群；不是金额RFM |
| item_repurchase | 同用户商品在不同日期再次观测到购买的7日代理，尾端单列 |

严格漏斗仅验证该指定路径；常见分支、同小时兼容路径与特征敏感性在后续任务继续。
没有金额、订单号或曝光，不计算真实订单数、GMV或CTR。
来源采集完整性不能只由最大时间戳证明；当前时间窗口按已知数据边界解释。

## 导入与完整校验

逐批验证注册Parquet及SHA-256，最多10万行/批。SQLite缓存64MiB，
排序可落本项目缓存磁盘。开启外键，事务失败回滚。
索引在完整导入后创建。未完成文件使用.building.sqlite，
只在完整性、外键、行数与六列规范值指纹全部一致后发布正式文件。

规范值指纹复用项目Pandas uint64行哈希再SHA-256方案，
是工程一致性核对；文件另有独立SHA-256。
SQLiteClient默认只读，SQL值使用参数绑定，大结果按批返回DataFrame，
小表超过max_rows时明确要求使用流式接口。

database_audit.json另将全量682,940个用户小时的10项指标与原始CSV独立核验结果逐值比较。
schema、索引、诊断SQL、策略及输入清单均保存指纹。

## 本轮范围

完成数据库、全部有效记录导入、索引、查询接口、SQL脚本和结果导出。
后续全维度特征、RFM代理分群、目标编码、未来7天预测预评估和完整EDA仍按台账推进。
