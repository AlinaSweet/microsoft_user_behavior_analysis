# 第一阶段第1项：资源配置样本验证

- 返回样本：每次 100,000 行；每种分块重复 2 次。
- 实际启动：2 个进程 worker，每个 1 个线程。
- 每个 worker 内存上限：1024.0 MiB。
- 每次只读取首个 CSV 分区；本报告不代表全量清洗或全文件性能。
- RSS 约每 0.1 秒采样一次，观测峰值可能漏掉更短暂的峰值。

| CSV 分块 | 耗时中位数（秒） | worker 观测内存峰值（MiB） | 内存上限占比 |
|---|---:|---:|---:|
| 32MiB | 1.3445 | 538.8 | 52.6% |
| 64MiB | 2.4024 | 528.5 | 51.6% |

初始分块选择 32 MiB，先限制单次解析规模；后续全量任务需根据吞吐量和内存重新评估。
详细原始测量保存在 engineering_benchmark.json，源数据 SHA-256 登记在 data/catalog/user_behavior_raw.json。

依据：[Dask worker 内存管理](https://distributed.dask.org/en/stable/worker-memory.html)、[CSV 分块读取](https://docs.dask.org/en/stable/generated/dask.dataframe.read_csv.html)。
