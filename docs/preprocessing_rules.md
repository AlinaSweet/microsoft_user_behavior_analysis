# 第一阶段第四项：类型压缩与基础中间表

2026-10-30当前补充：完整保留记录的标准事件和7张键/聚合表已在base_raw_v2生成，
正式特征位于features_raw_v2。统一入口见[current_datasets.json](../data/catalog/current_datasets.json)，
方法见[全维度特征说明](feature_system.md)。本页下文保留历史版本的复现规则。

## 当前适用范围

本页记录base_v1历史四元组归并口径。2026-10-24起第二阶段主表使用
data/catalog/validated_records_v1.json所登记的全部有效原记录；
旧事件和三张聚合表保留对照，不能把它们的计数直接当作原始记录量。
当前处理约定见[重复值策略](duplicate_policy.md)。

## 复现

在仓库根目录执行：

    bash scripts/run_project.sh preprocess \
      --catalog data/catalog/clean_v1.json \
      --policy configs/preprocessing.json \
      --output-dir data/processed/base_v1 \
      --report-dir outputs/reports/stage1_step4

输入来自上一项的完整事件集，按清单核对每个文件的大小、SHA-256、字段、行数与文件集合。数据输出目录必须不存在。读取为有界 Arrow 批次，不将整个文件或数据集载入 Pandas。

## 类型与字段选择

| 字段 | 存储处理 | 正确性依据 |
|---|---|---|
| event_id | 按全量范围选择 uint32 或 uint64 | 先检查最小/最大值，再安全转换；它是源记录序号 |
| user_id / item_id | 保留字符串 | 保留前导零，不把 ID 的数值大小当作特征 |
| category_id | 类别不超过配置上限时使用完整共享字典，索引 int16/int32；否则保留字符串 | 未知或空类目失败，不以 -1 静默代替 |
| behavior_type | uint8，仍是 1/2/3/4 | 校验真实编码，不改变含义 |
| event_time | 无时区 timestamp[ms] | 保留源小时值；安全转换不丢精度，不丢弃已有时区 |

规范事件只保留五个必要业务字段与源记录序号。原始 time/item_category 的重复别名、分块辅助信息及拒绝原因不进入模型事件表；其来源与拒绝记录仍在上一项产物中追溯。字典只是存储编码，模型词表仍须由训练部分独立拟合。

使用 Zstandard level 3、最多 131,072 行的 row group；具体策略在 preprocessing.json。类别集合最多收集 100,000 个；超过后使用字符串存储，避免词表无界增长。

## 三维聚合表

| 表 | 唯一键 | 指标 |
|---|---|---|
| user_daily_stats | user_id + event_date | 行为总次数、四种行为次数、不同商品数、首末行为时间 |
| item_daily_stats | item_id + event_date | 行为总次数、四种行为次数、不同用户数、首末行为时间 |
| time_hourly_stats | event_time | 行为总次数、四种行为次数、不同用户/商品数 |

聚合在磁盘暂存关系上全局分组，数据库缓存 64 MiB；并非只在各输入块内分组。计数列根据全量源行数上界选择 uint32/uint64；日键为 date32，时间为 timestamp[ms]。各表的行为总次数及分行为次数必须与完整事件集一致。

这些是全期基础统计。构造预测特征时只能汇总预测截点以前的日期/小时，不把全期统计直接回填历史样本。

## 完整验证与前序复核

1. 编码前后完整读回，按相同顺序和字段比较规范值哈希，并与上一项的结果指纹关联。
2. 独立 Dask 全局检查事件键和三种聚合键、空值与实体数。
3. 从完整事件独立重建每个用户日、商品日、小时分组的所有指标，完整外连接逐值比较，包括不同实体数和首末时间。总数一致不替代逐组比较。
4. 校验每份产物指纹，并重新执行第三项的全量清洗/统计/前序研究复核。
5. 运行项目全部编码规范、类型和测试门禁，feature CI 通过后同步 dev/main。

独立复核：

    PYTHONPATH=src .venv/bin/python scripts/audit_preprocessing.py

如需保留后续复核记录，应使用新的 --output 路径。

## 读写测量口径

同时保留同一事件集的规范 CSV、原清洗 Parquet 和压缩 Parquet。三者具有相同记录和字段；完整解码各重复两次并交替顺序。CSV 指定列类型，标识符保持字符串，读取缓冲为 16 MiB；Parquet 按批次读取。

文件系统缓存未受控，结果只作为本机完整解码观测，不能称冷缓存吞吐或其他引擎排名。压缩减小体积可能增加解码 CPU 成本，按真实结果分别报告。全流程耗时包含源校验、字典选择、编码、暂存、聚合、读回与测量，不作为单独写入吞吐。

PyArrow 26 缺少类型元信息，仅对其导入使用有原因说明的 import-untyped 例外；没有关闭项目整体类型检查，实际 Schema 与完整读回结果均受验证。

实现参考：[Arrow Parquet 写入接口](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.write_table.html)、[Arrow DictionaryArray](https://arrow.apache.org/docs/python/generated/pyarrow.DictionaryArray.html)。运行行为以本机锁定的 PyArrow 26 及实际验证为准。
