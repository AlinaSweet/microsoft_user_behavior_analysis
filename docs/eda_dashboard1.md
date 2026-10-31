# 看板一 EDA 方法与复现

## 范围与输入

看板一包含数据概览、用户与时间、商品与类目、行为路径与关联四个模块。
基线分析为26幅统计图，补充分析为8幅；PNG与SVG为同图的不同格式。

- 输入：data/processed/analysis_raw_v1/behavior.sqlite，只读访问。
- 有效原记录12,256,906条，用户10,000，商品2,876,947，类目8,916。
- 观测期：2025-11-18 00时至2025-12-18 23时，共31天、744小时。
- 全部有效记录保留；每用户小时超过90条仅标记；四元组6,213,379个供对照。
- 源小时不转换；时段分析采用微软中国与Asia/Shanghai业务约定，源时区未经独立核实。
- 日历中的周末为周六、周日。观测期不含中国大陆2025年法定节假日。

## 统计口径

| 指标或分析 | 定义与边界 |
|---|---|
| 原记录量 | 对原始日志条数计数，不解释为独立真实操作或订单 |
| 四元组量 | 用户、商品、行为、完整日期小时的不同组合数 |
| 用户日活跃 | 某自然日有有效记录的不同用户数 |
| 小时活跃 | 有记录的小时桶，不推算在线时长或会话 |
| 同窗购买覆盖 | 同窗口浏览用户商品对中也有购买的比例，不保证先后 |
| 严格跨小时路径 | 同一用户商品、时间严格递增、首次浏览后7天内；队列保留完整随访 |
| 下一活跃小时关联 | 小时间隔不超过24，允许同小时多行为，矩阵行和可大于100% |
| 用户未来标签 | 过去7天活跃用户在截点后7天是否有购买记录，三个截点分别统计 |
| 商品四象限 | 至少20个浏览用户商品对的11,268件商品；平滑先验权重20 |
| 排名门槛 | 商品至少50个浏览用户商品对、类目至少200对，按Wilson下界排序 |

无曝光、金额、订单号、分钟秒时间及类目名称映射，因此不输出CTR、GMV、客单价、
真实订单复购、停留时长、小时内真实先后或匿名类目的业务名称。
路径可能重叠，不能直接相加；置信区间未校正同用户聚类和多重比较，仅用于描述。

## 基线结果

- 31天购买用户覆盖88.86%；购买记录占全部记录约0.98%，分母不同。
- 头部20%类目贡献94.46%浏览记录。
- 12月12日购买用户占当日日活50.48%；没有活动日志，不作促销归因。
- 成熟浏览队列3,581,365个用户商品对；严格跨小时浏览后购买38,215对，
  浏览后加购再购买6,397对，浏览后收藏再购买875对，指定四步路径67对。
- 三个未来用户队列只含历史7天活跃用户；正式特征用户表另含截至截点全部已观测用户，
  两个人群口径不可互换。

## 补充分析

补充结果位于outputs/reports/eda_extension_20261029/。

- 依历史记录量分位组和过去有无购买分层，组内有无目标行为各至少30人才纳入直接标准化。
- 有加购组未来7天购买比例在三个截点分别高出6.38、9.47、8.77个百分点。
- 原记录与四元组用户排名Spearman为0.9943，前10%重合914人，重合率91.4%。
- 类目购买间隔与跨日期复购代理留足随访，保留支持量；不解释为订单复购。
- RF为无金额代理；SVD和共现覆盖、候选字段相关性用于诊断，未完成正式有效性筛选。
- 结果为观察关联，不作因果或独立模型效果结论。

## 产物与配置

| 位置 | 内容 |
|---|---|
| outputs/reports/eda_dashboard1_20261029/dashboard.html | 四模块离线看板 |
| outputs/reports/eda_dashboard1_20261029/tables.md | 基线对应统计表 |
| outputs/reports/eda_dashboard1_20261029/analysis.json | 基线完整聚合结果 |
| outputs/reports/eda_dashboard1_20261029/figures/ | 26幅PNG及SVG |
| outputs/reports/eda_extension_20261029/ | 8幅补充图、6份CSV及2份分析JSON |
| data/processed/eda_dashboard1_20261029/ | 本地EDA汇总缓存 |
| configs/eda_dashboard1.json | 分析窗口、截点、门槛及间隔 |
| scripts/run_eda.py | 基线统计与重绘入口 |
| sql/eda/ | 汇总及分析SQL |
| configs/feature_system.json、scripts/run_features.py | 补充分析与特征构建配置及入口 |

## 复现

在仓库根目录执行：

```bash
MPLCONFIGDIR=.cache/matplotlib PYTHONPATH=src .venv/bin/python scripts/run_eda.py
MPLCONFIGDIR=.cache/matplotlib PYTHONPATH=src .venv/bin/python scripts/run_eda.py --render-only
```

补充分析的eda阶段执行分层与排名比较，reports阶段依赖已完成特征快照：

```bash
MPLCONFIGDIR=.cache/matplotlib PYTHONPATH=src .venv/bin/python scripts/run_features.py --phase eda
MPLCONFIGDIR=.cache/matplotlib PYTHONPATH=src .venv/bin/python scripts/run_features.py --phase reports
```

HTML支持图组切换或主题搜索；任意日期、人群与类目的全局联动重算尚未实现。
基线执行证据见[execution_record.json](../outputs/reports/eda_dashboard1_20261029/execution_record.json)，
特征及补充分析质量证据见[交付报告](../outputs/reports/feature_system_20261029/README.md)。
