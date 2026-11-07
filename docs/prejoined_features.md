# 预拼接特征宽表

## 当前交付

直接复用 `features_raw_v2` 四截点现有 `model_inputs`，完成独立全量连接与源值审计后，
登记到 [prejoined_wide_v1.json](../data/catalog/prejoined_wide_v1.json)。
后续筛选按目录选择截点和列，无需重复连接实体表。

| 截点 | 候选行数 | 分片 | 标量特征 | 身份和覆盖字段 |
|---|---:|---:|---:|---:|
| 2025-11-25 | 1,030,893 | 16 | 439 | 7 |
| 2025-12-02 | 1,061,515 | 16 | 439 | 7 |
| 2025-12-09 | 1,117,324 | 16 | 439 | 7 |
| 2025-12-19 | 1,216,917 | 16 | 439 | 7 |

四截点合计4,426,649行快照；同一组合可跨截点再次出现。16分片按用户哈希分行，
每个文件都是相同的446列，不是按列拆成16份。
439包含用户130、商品90、类目73、用户商品72、用户类目69、时间5。
三类核心实体共有293个特征，可以通过目录中的字段所属表选择；不再复制另一套大表。
6类原始序列数组保留独立文件，没有塞入这446列。

## 粒度和来源

唯一键为 `as_of_time,user_id,item_id`，类目由商品关系提供。
候选只来自截点前7天已交互组合。所有输入使用同一截点、完整记录版本。
原有生成流程按单截点目录隔离时间；本次审计显式把时间纳入连接键。

| 来源 | 审计连接键 |
|---|---|
| user_features | as_of_time,user_id |
| item_features | as_of_time,item_id,category_id |
| category_features | as_of_time,category_id |
| pair_features | as_of_time,user_id,item_id,category_id |
| user_category_features | as_of_time,user_id,category_id |
| time_features | as_of_time |

先检查每个源表键唯一、非空、截点一致和源事件严格早于截点。
再从候选宽表逐个LEFT JOIN源表，检查未匹配与连接行数；不会用去重掩盖源表键冲突。
对全部439列进行NULL安全的逐值比较，并分别检查类型。
候选的身份、类目、来源最大时间和历史覆盖字段做双向集合比较，防止相同行数掩盖丢行与增行。
商品对应多个类目时拒绝通过。

## 缺失与高级特征覆盖

[本次字段画像](../outputs/reports/prejoined_wide_20261107/field_profiles.json)
使用候选行数作为分母；它与实体表画像的用户数、商品数分母不同。
每列记录缺失率、零值率、非有限数、来源表、业务缺失策略及未匹配来源行数。
只有所有连接和源值比较通过后，才将原有空值登记为匹配源表中的缺失。

无观测购买的最近购买间隔、分母为零的比率保持原有NULL，不统一填0。
SVD和共现未知情况按原规则保留0及可用标记；另统计
`pair_svd_available`、`pair_cooc_graph_known`，不以无空值宣称全覆盖。
本步骤没有设筛选阈值，没有删除特征，也没有拟合编码、标准化或预测模型。

## 分批读取

在项目根目录预览指定列：

```bash
PYTHONPATH=src .venv/bin/python scripts/read_wide_features.py \
  --anchor 2025-12-09 \
  --columns as_of_time user_id item_id user_event_count_7d \
    item_buy_count_7d category_buy_count_7d \
  --limit 5
```

供筛选程序调用的接口：

```python
from pathlib import Path

from user_behavior_analysis.dao.wide_repository import iter_wide_features

catalog = Path("data/catalog/prejoined_wide_v1.json")
columns = ["as_of_time", "user_id", "item_id", "user_event_count_7d"]
for batch in iter_wide_features(catalog, "2025-12-09", columns, batch_size=8192):
    print(batch.num_rows)
```

每次打开先验证通过的审计报告及该截点所有分片SHA-256，然后只解码选中列，按批返回Arrow数据。
指纹验证需要顺序读取文件一次；不是每个批次重复验证。
列必须来自已审计目录，不能加入标签、重复列或任意SQL表达式；批次范围为1至100000行。
报告、分片、目录、行数或Schema不一致时拒绝读取。原有NULL和字段顺序均保留。

## 重新验收与发布

```bash
PYTHONPATH=src .venv/bin/python -u scripts/audit_wide_features.py \
  --report-dir outputs/reports/prejoined_wide_YYYYMMDD_02 \
  --catalog data/catalog/prejoined_wide_v2.json
```

必须提供新的报告目录和目录文件名。失败保留失败报告，不发布通过目录。
全量核验来源与宽表文件在运行前后指纹一致，不改写Parquet，也不修改历史特征值。
本次证据见[验收报告](../outputs/reports/prejoined_wide_20261107/README.md)。

标签继续独立保存。当前宽表是一行用户商品对，已有 `user_targets` 是用户级未来购买；
两者不能直接当成同一个预测任务。12月19日未来标签不可用，不能填成0。
大型数据保持本地，Git同步目录、审计报告、代码和方法。
