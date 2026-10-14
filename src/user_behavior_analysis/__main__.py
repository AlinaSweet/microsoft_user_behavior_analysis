"""Stage 1.1 command-line entry point: check, benchmark, register, verify."""
import argparse
from datetime import datetime, timezone
import gc
from importlib import metadata
import json
from pathlib import Path
import statistics
import sys
import time

import dask.dataframe as dd
from dask.utils import parse_bytes
import psutil

from .artifacts import check_git_files, register, sha256_file, write_json
from .runtime import ROOT, inspect_worker, load_config, read_sample, resolve_source, resource_plan, start_client


def packages():
    return {name: metadata.version(name) for name in ('pandas', 'numpy', 'dask', 'distributed', 'pyarrow', 'psutil', 'PyYAML')}


def check(config, source):
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Project requires Python 3.12')
    plan = resource_plan(config)
    with start_client(config, plan) as client:
        workers = client.run(inspect_worker)
        if len(workers) != plan['n_workers'] or len({state['pid'] for state in workers.values()}) != plan['n_workers']:
            raise RuntimeError('Worker process count differs from the resource plan')
        for state in workers.values():
            if state['threads'] != plan['threads_per_worker']:
                raise RuntimeError('Worker thread count differs from the resource plan')
            if state['thresholds'] != config['distributed']['worker']['memory']:
                raise RuntimeError('Worker memory thresholds were not applied')
            if state['memory_limit_bytes'] != plan['memory_limit_bytes']:
                raise RuntimeError('Worker memory limit differs from the resource plan')
        frame = dd.read_csv(str(source), blocksize=parse_bytes(config['local_cluster']['csv_blocksize']),
                            encoding=config['data']['encoding'],
                            dtype={column: 'string[pyarrow]' for column in config['data']['columns']})
        partition_count = frame.npartitions
        sample = client.compute(frame.head(1000, npartitions=1, compute=False)).result(timeout=90)
        if sample.columns.tolist() != config['data']['columns']:
            raise RuntimeError('Sample column check failed')
    git_files = check_git_files()
    if git_files['issues']:
        raise RuntimeError('; '.join(git_files['issues']))
    report = {
        'status': 'passed', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'python': sys.version.split()[0], 'packages': packages(),
        'sample_rows': len(sample), 'columns': sample.columns.tolist(),
        'applied_csv_blocksize': config['local_cluster']['csv_blocksize'],
        'csv_partition_count': partition_count,
        'source_size_bytes': source.stat().st_size,
        'source_is_local_symlink': source.is_symlink(),
        'resource_plan': plan, 'actual_workers': workers, 'git_files': git_files,
    }
    write_json(ROOT / 'outputs/reports/environment_check.json', report)
    return report


def benchmark(config, source, rows=None, repeats=None):
    rows = config['benchmark']['sample_rows'] if rows is None else rows
    repeats = config['benchmark']['repeats'] if repeats is None else repeats
    if rows <= 0 or repeats <= 0:
        raise ValueError('Sample rows and repeats must be positive')
    plan = resource_plan(config)
    blocks = list(dict.fromkeys([config['local_cluster']['csv_blocksize'], *config['benchmark']['block_sizes']]))
    trials = []
    started = time.perf_counter()
    with start_client(config, plan) as client:
        # Load modules before measuring; results remain bounded to a sample.
        warmup = client.submit(read_sample, str(source), 1000, config['data']['encoding'], config['data']['columns']).result(timeout=90)
        del warmup
        client.run(gc.collect)
        initial_workers = client.run(inspect_worker)
        for repeat in range(repeats):
            order = blocks if repeat % 2 == 0 else list(reversed(blocks))
            for block in order:
                frame = dd.read_csv(str(source), blocksize=parse_bytes(block),
                                    encoding=config['data']['encoding'],
                                    dtype={column: 'string[pyarrow]' for column in config['data']['columns']})
                # Read only the first partition, then return the requested rows.
                lazy = frame.head(rows, npartitions=1, compute=False)
                before = client.run(inspect_worker)
                peaks = {address: info['rss_bytes'] for address, info in before.items()}
                driver_peak = psutil.Process().memory_info().rss
                tick = time.perf_counter()
                future = client.compute(lazy)
                deadline = tick + 120
                while not future.done():
                    if time.perf_counter() > deadline:
                        future.cancel()
                        raise TimeoutError('Sample read exceeded 120 seconds; reduce sample or block size')
                    for address, info in client.run(inspect_worker).items():
                        peaks[address] = max(peaks.get(address, 0), info['rss_bytes'])
                    driver_peak = max(driver_peak, psutil.Process().memory_info().rss)
                    time.sleep(0.1)
                sample = future.result(timeout=5)
                elapsed = time.perf_counter() - tick
                for address, info in client.run(inspect_worker).items():
                    peaks[address] = max(peaks.get(address, 0), info['rss_bytes'])
                if len(sample) != rows:
                    raise RuntimeError('First partition contained fewer than the requested sample rows')
                trials.append({
                    'block_size': block, 'repeat': repeat + 1, 'returned_sample_rows': len(sample),
                    'csv_partition_count': frame.npartitions, 'wall_seconds': round(elapsed, 4),
                    'sample_memory_bytes': int(sample.memory_usage(deep=True).sum()),
                    'observed_worker_peak_rss_bytes': max(peaks.values()),
                    'observed_driver_peak_rss_bytes': driver_peak,
                    'worker_peak_fraction': round(max(peaks.values()) / plan['memory_limit_bytes'], 4),
                    'status': 'passed',
                })
                del sample, future, frame, lazy
                client.run(gc.collect)
        final_workers = client.run(inspect_worker)
        if {v['pid'] for v in initial_workers.values()} != {v['pid'] for v in final_workers.values()}:
            raise RuntimeError('A worker restarted during the sample benchmark')
    summary = []
    for block in blocks:
        group = [trial for trial in trials if trial['block_size'] == block]
        summary.append({
            'block_size': block, 'median_wall_seconds': round(statistics.median(t['wall_seconds'] for t in group), 4),
            'max_observed_worker_rss_bytes': max(t['observed_worker_peak_rss_bytes'] for t in group),
            'max_worker_peak_fraction': max(t['worker_peak_fraction'] for t in group),
        })
    raw_manifest, fingerprint = register(source, 'user_behavior_raw', 'raw',
                                         'User-provided CSV; supply the same content via --data or USER_BEHAVIOR_CSV')
    report = {
        'status': 'passed', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'First CSV partition per trial; bounded returned sample. Not a full-file benchmark.',
        'sample_rows': rows, 'repeats': repeats, 'resource_plan': plan,
        'configured_block_size': config['local_cluster']['csv_blocksize'],
        'config_sha256': sha256_file(ROOT / 'configs/dask.yaml'), 'source_sha256': fingerprint['sha256'],
        'packages': packages(), 'worker_restart_count': 0,
        'monitoring': 'Worker RSS sampled approximately every 0.1 seconds; brief peaks may be missed.',
        'cluster_and_trials_seconds': round(time.perf_counter() - started, 4),
        'summary': summary, 'trials': trials,
    }
    write_json(ROOT / 'outputs/reports/engineering_benchmark.json', report)
    lines = ['# 第一阶段第1项：资源配置样本验证', '',
             f'- 返回样本：每次 {rows:,} 行；每种分块重复 {repeats} 次。',
             f'- 实际启动：{plan["n_workers"]} 个进程 worker，每个 {plan["threads_per_worker"]} 个线程。',
             f'- 每个 worker 内存上限：{plan["memory_limit_bytes"] / 2**20:.1f} MiB。',
             '- 每次只读取首个 CSV 分区；本报告不代表全量清洗或全文件性能。',
             '- RSS 约每 0.1 秒采样一次，观测峰值可能漏掉更短暂的峰值。', '',
             '| CSV 分块 | 耗时中位数（秒） | worker 观测内存峰值（MiB） | 内存上限占比 |',
             '|---|---:|---:|---:|']
    for item in summary:
        lines.append(f'| {item["block_size"]} | {item["median_wall_seconds"]:.4f} | {item["max_observed_worker_rss_bytes"] / 2**20:.1f} | {item["max_worker_peak_fraction"]:.1%} |')
    lines.extend(['', '初始分块选择 32 MiB，先限制单次解析规模；后续全量任务需根据吞吐量和内存重新评估。',
                  '详细原始测量保存在 engineering_benchmark.json，源数据 SHA-256 登记在 data/catalog/user_behavior_raw.json。',
                  '', '依据：[Dask worker 内存管理](https://distributed.dask.org/en/stable/worker-memory.html)、[CSV 分块读取](https://docs.dask.org/en/stable/generated/dask.dataframe.read_csv.html)。'])
    (ROOT / 'outputs/reports/engineering_benchmark.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description='阶段 1.1 环境、Dask 资源与数据产物管理')
    parser.add_argument('--config', help='配置文件路径，默认为 configs/dask.yaml')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('check', 'benchmark'):
        sub = commands.add_parser(name)
        sub.add_argument('--data', help='CSV 路径；优先级高于 USER_BEHAVIOR_CSV')
        if name == 'benchmark':
            sub.add_argument('--rows', type=int)
            sub.add_argument('--repeats', type=int)
    sub = commands.add_parser('register', help='登记大型文件的校验清单')
    sub.add_argument('--path', required=True)
    sub.add_argument('--name', required=True)
    sub.add_argument('--kind', choices=['raw', 'interim', 'processed'], required=True)
    sub.add_argument('--recipe', required=True, help='来源说明或可复现的生成命令')
    sub.add_argument('--share-location', help='已确认的共享位置；不要填写密码或带令牌的链接')
    sub = commands.add_parser('verify', help='按校验清单验证文件内容')
    sub.add_argument('--manifest', required=True)
    sub.add_argument('--path', required=True)
    commands.add_parser('check-git', help='检查 Git 已跟踪文件的大小和目录规则')
    args = parser.parse_args()
    try:
        if args.command == 'check-git':
            result = check_git_files()
            if result['issues']:
                raise ValueError('; '.join(result['issues']))
        elif args.command == 'register':
            output, result = register(args.path, args.name, args.kind, args.recipe, args.share_location)
            result = {'manifest': str(output.relative_to(ROOT)), **result}
        elif args.command == 'verify':
            manifest = Path(args.manifest)
            path = Path(args.path)
            if not manifest.is_absolute(): manifest = ROOT / manifest
            if not path.is_absolute(): path = ROOT / path
            expected = json.loads(manifest.read_text(encoding='utf-8'))
            matches = path.stat().st_size == expected['size_bytes'] and sha256_file(path) == expected['sha256']
            if not matches:
                raise ValueError('File differs from its manifest')
            result = {'status': 'passed', 'sha256': expected['sha256']}
        else:
            config = load_config(args.config)
            source = resolve_source(config, args.data)
            result = check(config, source) if args.command == 'check' else benchmark(config, source, args.rows, args.repeats)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, FileNotFoundError, TimeoutError, KeyError) as error:
        print(f'操作失败：{error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
