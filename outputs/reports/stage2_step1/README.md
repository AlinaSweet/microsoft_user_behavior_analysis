# 第二阶段第一项：SQLite 与完整 SQL 分析

## 已交付内容

- 第三范式数据库，包含行为、用户、商品、类目、日期、时间、行为类型和来源元数据八张持久表；canonical_events / calendar_features 两个视图。
- 完整 6,213,379 条行为，10,000 名用户，2,876,947 个商品，8,916 个类目，744 个小时与 31 个日期。
- 固定上限批次导入、参数化 SQL、主键/唯一键/外键/STRICT 类型、查询索引与 ANALYZE。
- 11 类基础和复杂 SQL，完整导出 6,316,278 行、136 个 Parquet 文件；预览行不替代完整结果。
- 只读 Python-SQLite-Pandas 工具，支持小结果预算及大结果分块。

数据库文件：data/processed/sqlite_v1/behavior_store.sqlite，1,795,801,088 字节（1.672 GiB，含全部表和索引）。大型文件按既定政策保留在项目数据目录，Git 同步代码、SQL、小报告和校验清单。

## 完整性和前一阶段复核

独立审计 9 项总门禁全部通过。通过 Arrow 和原生 SQLite 游标比较全部源事件的六列值，差异 0；全部 11 类查询导出的每列每行与原生查询结果一致，差异 0。检查包括 NULL、列顺序、行数、额外记录、文件集合和所有文件指纹。

数据库、Parquet 和前序清洗的规范值 SHA-256 一致：e612feaf1cfd7314867b3bec456cba8f44701d15abe4b8bf7d89b6ab0d32f60f。

前一完整阶段重新复核通过：全部 74 项测试、格式/类型/规范门禁、真实 Dask worker 环境、五篇论文与七份研究文件、完整清洗/IQR/3σ、原始与中间文件指纹、三张基础聚合表的全部分组指标。审计不把 CI 成功当成数据正确性证明。

| 执行内容 | 代码版本 |
|---|---|
| 数据库完整构建 | 1d6d53ba6fdab9cf34046ddd12cfad31ae7a8945 |
| SQL 完整导出 | d36150ccb99ac6207409c0ddfa4667cf6cb15f90 |
| 独立数据审计与上一完整阶段回归 | 610155581be2458a2be1c2481aa7948a5118adc2 |

实现代码 6101555 的 feature Quality #18 已通过（1 分 25 秒）。云端交付按 feature → dev → main，同一提交的 Quality 通过后合入并分别确认。状态入口为 https://github.com/AlinaSweet/microsoft-store-user-behavior-analysis/actions 。

## 全量查询结果及本机程序计时

观察区间：[2025-11-18 00:00:00, 2025-12-19 00:00:00)，保留源小时值。时间按用户指定微软中国背景和 Asia/Shanghai 假设解释，源时区未独立确认。

| 查询 | 完整输出行数 | 取数及序列化计时（秒） |
|---|---:|---:|
| overview | 1 | 130.9074 |
| behavior_distribution | 4 | 2.8757 |
| daily_active | 31 | 3.5058 |
| weekly_active | 5 | 7.6901 |
| popular_items | 50 | 78.6430 |
| popular_categories | 50 | 84.6365 |
| user_sequences | 6,213,379 | 87.0709 |
| funnel_reach | 4 | 26.5784 |
| strict_funnel | 1 | 118.4948 |
| user_proxy_segments | 10,000 | 12.7170 |
| item_repurchase | 92,753 | 1.4979 |

计时使用程序的 perf_counter，包含查询和 Parquet 序列化，文件系统缓存未受控；不把电脑暂停前后的历法时间差解释为 CPU 耗时。数据库完整构建计时 545.8729 秒；批次边界观测驱动 RSS 最大 307.27 MiB，可能漏掉其他阶段的短暂峰值。

## 漏斗与复购口径

严格链路为同一用户商品对“首次观测浏览 → 加购 → 收藏 → 购买”，各步小时严格递增，并在首次浏览后七天内。4,677,501 个浏览对中，3,581,365 个具完整后续窗口；另 1,096,136 个后续观察不足，单列为右截断。可完整观察的链路依次为：

| 阶段 | 用户商品对数 |
|---|---:|
| 浏览 | 3,581,365 |
| 加购 | 74,573 |
| 收藏 | 768 |
| 购买 | 67 |

67 仅指满足上述完整且严格顺序定义的用户商品对。全期购买行为记录为 106,678；链路缺步、同小时顺序未知和不同窗口都会影响漏斗，不能把该链路数解释为真实订单量或全站总体转化。

商品复购结果覆盖 92,753 个有购买记录的商品。共 102,996 个观测购买用户商品对，其中 73,033 个具完整七天后续观察，1,406 个在窗口内另一个日期再次出现购买记录；按这些完整观察对加权的重复记录比例为 1.9252%。跨商品求和的单位是用户商品对，不是全站去重用户；记录不包含订单号或件数。

## 无金额条件下的透明分群基线

用户已明确接受购买行为代理。R 为距最后观测日的最近购买天数，F 为有购买记录的不同日期数，M_count 为去重后的购买行为记录数；不称消费金额或完整金额型 RFM。

| 行为代理分群 | 用户数 | 购买记录数 |
|---|---:|---:|
| 流失风险代理 | 303 | 742 |
| 沉睡行为代理 | 173 | 244 |
| 高价值行为代理 | 5,059 | 89,938 |
| 潜力行为代理 | 4,465 | 15,754 |

购买日数与购买次数的 Spearman 相关：全部 10,000 用户 0.9213；仅已购用户 0.8878。二者信息重叠明显，后续特征筛选须检查冗余。阈值定义见 docs/sqlite_analysis.md；这些是全期描述性分群，后续预测按历史截点重新构造特征。

## 索引观测

三个 COUNT 查询均通过 EXPLAIN 确认使用覆盖索引；索引与 NOT INDEXED 的结果一致。

| 例查询 | 匹配行 | 索引中位数（秒） | 强制扫描中位数（秒） |
|---|---:|---:|---:|
| user_time | 1,406 | 0.001710 | 0.893215 |
| item_behavior | 0 | 0.000873 | 0.815687 |
| time_range | 186,278 | 0.016800 | 0.900802 |

每种方式只测两次、顺序交替，缓存未受控，计时包含连接创建。商品例查询匹配为 0，属于未命中查询。上述点查结果不代表全量分组和窗口查询也达到同样耗时；完整查询计时在上表分别记录。

## 发现并修正的问题

本机首次完整 SQL 作业在原生引擎初始化后设置 SQLITE_TMPDIR，实测仍将部分排序缓存写到系统临时目录。已将设置前移到 Python 启动入口和包初始化阶段；小探针与新的完整数据审计进程均实际观测到项目 .cache/sqlite 内的临时文件，未使用已弃用的全局目录 PRAGMA。原数据库和查询结果始终输出于项目规定目录。

修正前证据：runtime_tempdir_before.json；启动探针：runtime_tempdir_audit.json；完整审计实际路径：../stage2_step1_audit_20261015_01/runtime_paths.json。历史测量保留，修正另有提交与回归记录。

## 复现与文件入口

    bash scripts/run_project.sh build-db
    bash scripts/run_project.sh analyze-db
    PYTHONPATH=src .venv/bin/python scripts/audit_database.py \
      --output-dir outputs/reports/stage2_step1_audit_YYYYMMDD_NN

复跑须选择新的数据库、数据输出和审计目录。默认产物已存在时会明确停止，避免覆盖历史。

- 数据库清单：data/catalog/behavior_store_v1.json。
- 查询清单：data/catalog/sql_analysis_v1.json；完整结果：data/processed/sql_analysis_v1/。
- 机器报告：database.json、analysis.json、descriptive_summary.json。
- 完整独立审计：../stage2_step1_audit_20261015_01/audit.json；上一阶段报告在其 previous_stage1/。
- 操作和语义说明：docs/sqlite_analysis.md；表结构及查询：sql/；Python 接口：src/user_behavior_analysis/dao/sqlite_client.py。

下一项是全维度特征体系：生命周期、序列、SVD/共现/关联、代理价值与偏好特征。当前基线结果不替代该项的完整特征构建与有效性评估。
