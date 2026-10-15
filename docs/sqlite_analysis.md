# 第二阶段第一项：SQLite 与 SQL 分析

## 复现命令

在仓库根目录运行：

```bash
bash scripts/run_project.sh build-db
bash scripts/run_project.sh analyze-db
```

默认输入 data/catalog/base_v1.json；数据库 data/processed/sqlite_v1/behavior_store.sqlite；全量查询结果 data/processed/sql_analysis_v1/；报告 outputs/reports/stage2_step1/。这些大型数据目录被 Git 排除，代码、SQL、清单和小报告可同步。

每个命令都要求新数据输出路径。先使用 .building.sqlite 构建，完整验证通过后才发布最终数据库文件。失败时保留构建文件供诊断，重试应另指定新数据库路径或检查失败原因，不能把半成品当成完成结果。

## 第三范式与依赖

| 持久表 | 主键 | 其他属性与依赖 |
|---|---|---|
| users | user_id | 仅观察到的用户标识，不伪造注册或人口属性 |
| categories | category_id | 仅类目标识 |
| items | item_id | item_id → category_id；全量导入时拒绝跨批次类目变化 |
| calendar_dates | event_date | 仅观察到的日期 |
| event_times | event_time | event_time → event_date；源小时精度 |
| behavior_types | behavior_type | 唯一名称 pv / fav / cart / buy |
| behaviors | event_id | 用户、商品、行为类型、时间外键；四元组也是唯一候选键 |
| dataset_metadata | metadata_key | 每个来源元数据键对应一个值 |

行为表不重复存储 category_id、日期、星期或周末标记；它们分别由商品/时间外键或视图取得。实体表的非键属性依赖候选键，不在行为表中产生“商品 → 类目”的传递依赖。calendar_features 视图计算星期、周末、周一日期；周末不等同于法定休息日或调休工作日。

canonical_events 视图恢复与 Parquet 相同的六列事件，按源 event_id 顺序完整读回并比较规范值指纹。

## 导入、完整性和资源

- Unix/Mac 的 SQLite 临时排序和聚合文件通过进程内 SQLITE_TMPDIR 指向项目 .cache/sqlite，不使用已弃用的全局 PRAGMA；源文件和最终产物仍按各自目录管理。
- 固定 100,000 行批次（可配置，最大 200,000），数据库缓存 64 MiB，临时分组可落盘。
- 参数化 executemany 插入暂存表；每批事务内写入实体维表及行为表，拒绝跨批次重复和类目冲突。
- 每个连接显式启用外键；NOT NULL、正整数、行为枚举、小时对齐、唯一键和外键均受约束。
- 导入前后复验全部源文件指纹，检查完整数据库 integrity_check、foreign_key_check、行数和六列规范值 SHA-256。
- 构建报告保存源码提交、SQL 指纹、数据库指纹、实体数、全流程耗时和批次边界观测 RSS；该 RSS 不是持续采样的绝对峰值。

## 查询目录与业务口径

sql/queries 包含 11 个可独立运行的参数化查询，全部结果分块导出 Parquet；analysis.json 中的前 20 行只作为预览。

| 查询 | 范围/口径 |
|---|---|
| overview | 全期事件、用户/商品/类目及时间范围 |
| behavior_distribution | 四种行为的记录数、占比和不同用户数 |
| daily_active | 按源日期去重用户；完整日表 |
| weekly_active | 周一开周的自然周，注明实际观察天数；边界可能不足七天 |
| popular_items / popular_categories | 按购买行为记录数、总行为数排名前 50；不是销售额排名 |
| user_sequences | 所有用户的完整记录顺序、相邻记录间隔和同小时数量 |
| funnel_reach | 不要求顺序的阶段触达；不同阶段人数可能不单调 |
| strict_funnel | 同一用户商品对首次观测浏览 → 加购 → 收藏 → 购买，小时严格递增，七天内 |
| user_proxy_segments | RF 与购买行为次数的四类行为代理分群 |
| item_repurchase | 具完整七天观察的购买用户商品对，七天内另一个日期出现购买记录的用户比例 |

严格漏斗以首次观测浏览为锚点；窗口为 [首次浏览, 首次浏览+7天)，后续各步严格晚于上一步。后续观察不足七天的浏览对单独列为 right_censored_pairs，排除在各转化阶段分母外。同小时先后不可辨，不能用 event_id 证明真实顺序。缺少某一步不等于真实流程失败，日志可能不包含完整业务链路。

复购是购买日志的不同日期重复代理；同日多条记录不直接当作复购，不声称存在订单号或购买件数。首次购买窗口之前可能已有真实购买，本口径是“首次观测购买”。

当前 SQL 分群为透明阈值基线：最近七个观测日内购买、购买日期至少 3 天、购买记录至少 5 条为 high_value_proxy；其余最近七个观测日活跃者为 potential_proxy；闲置 7–13 天为 churn_risk_proxy；其余为 dormant_proxy。最近购买相对最后观测日计算，未购买的 R 保留空值。它不含金额，不能称完整金额型 RFM。后续特征任务会进一步计算代理得分、关联性与敏感性。

全期 SQL 用于描述性分析，不把全期分群和统计直接作为历史预测特征。

## Python 与 Pandas 接口

```python
from user_behavior_analysis.dao.sqlite_client import SQLiteClient

client = SQLiteClient("data/processed/sqlite_v1/behavior_store.sqlite")
frame = client.query_frame(
    "SELECT * FROM users WHERE user_id = :user",
    {"user": "001"},
    max_rows=1000,
)
for chunk in client.iter_frames(
    "SELECT * FROM canonical_events ORDER BY event_id",
    chunk_rows=50000,
):
    print(len(chunk))
```

接口使用 SQLite mode=ro 和 query_only；值通过 parameters 绑定，不拼接到 SQL。小 DataFrame 接口超过预算直接报错；大查询使用生成器。提前停止迭代时显式关闭生成器或用 contextlib.closing 管理。数据类型保留字符串 ID，SQL NULL 保留缺失值。

## 索引和性能证据

sql/indexes.sql 为用户时间、商品行为、行为时间、时间用户、商品类目及日期连接建索引，并执行 ANALYZE。analysis.json 记录 EXPLAIN QUERY PLAN。

同时对三个相同 COUNT 查询分别使用正常计划和 NOT INDEXED 强制扫描，各两次、顺序交替，先验证结果相同再比较耗时。缓存未受控，测量包含新建只读连接，不据此承诺所有查询均加速。

质量缓存已纳入全部 configs 的 JSON/YAML 与 SQL 文件，防止查询变化后复用旧的测试成功结果；云端仍强制重新运行。

## 完整独立复核与前一阶段回归

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_database.py \\
  --output-dir outputs/reports/stage2_step1_audit_YYYYMMDD_NN
```

每次使用新的审计目录。原生 SQLite 游标通过独立 JOIN 恢复六列，用 Arrow 逐批比较每个值，不依赖导入流程的 Pandas 哈希。另将每个完整查询结果与原生 SQL 游标逐值比较，核对文件指纹、文件集合、列顺序、行数、额外记录和 NULL；业务含义由已知结果场景测试补充验证。

审计包含“行为编码改成另一合法值、总行数不变、完整性与外键仍通过”的负向场景，要求逐值审计明确失败。完整审计随后调用 audit_stage1.py，重新验证上一完整阶段的质量、环境、研究、清洗及聚合，不只检查第二阶段新增文件。

## 参考接口文档

- [SQLite 临时文件位置](https://www.sqlite.org/tempfiles.html)
- [SQLite 外键与每连接启用要求](https://www.sqlite.org/foreignkeys.html)
- [SQLite 查询计划与索引](https://www.sqlite.org/queryplanner.html)
- [SQLite 窗口函数](https://www.sqlite.org/windowfunctions.html)
- [Pandas 参数化、分块读取接口](https://pandas.pydata.org/docs/reference/api/pandas.read_sql_query.html)

运行行为以锁定的本机版本、合成场景测试和完整真实数据报告为准。
