"""Resolve source paths and explicitly apply resource settings to Dask."""
from contextlib import contextmanager
import csv
import os
from pathlib import Path

import dask
from dask.utils import parse_bytes
import pandas as pd
import psutil
import yaml
from distributed import Client, LocalCluster

ROOT = Path(__file__).resolve().parents[2]


def load_config(path=None):
    config_path = Path(path) if path else ROOT / 'configs/dask.yaml'
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    with config_path.open(encoding='utf-8') as handle:
        config = yaml.safe_load(handle)
    limits = config['distributed']['worker']['memory']
    values = [limits[key] for key in ('target', 'spill', 'pause', 'terminate')]
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        raise ValueError('Dask memory thresholds must be numeric')
    if not (0 < values[0] < values[1] < values[2] < values[3] < 1):
        raise ValueError('Dask memory thresholds must be strictly increasing between 0 and 1')
    local = config['local_cluster']
    for key in ('n_workers', 'threads_per_worker'):
        if not isinstance(local[key], int) or isinstance(local[key], bool) or local[key] < 1:
            raise ValueError(f'{key} must be a positive integer')
    fraction = local['available_memory_fraction']
    if not isinstance(fraction, (int, float)) or not 0 < fraction < 1:
        raise ValueError('available_memory_fraction must be between 0 and 1')
    for key in ('memory_limit', 'csv_blocksize', 'minimum_worker_memory'):
        if parse_bytes(local[key]) <= 0:
            raise ValueError(f'{key} must be positive')
    scratch = (ROOT / local['local_directory']).resolve()
    if not scratch.is_relative_to(ROOT):
        raise ValueError('Dask scratch directory must stay inside the project')
    if not config['data']['columns'] or len(set(config['data']['columns'])) != len(config['data']['columns']):
        raise ValueError('Expected CSV columns must be nonempty and unique')
    return config


def resolve_source(config, override=None, env=None):
    environment = os.environ if env is None else env
    raw = override or environment.get('USER_BEHAVIOR_CSV') or config['data']['default_path']
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f'CSV not found: {path}. Use --data or USER_BEHAVIOR_CSV to specify it.')
    with path.open(encoding=config['data']['encoding'], newline='') as handle:
        header = next(csv.reader(handle), [])
    expected = config['data']['columns']
    if header != expected:
        raise ValueError(f'CSV columns differ: expected {expected}, found {header}')
    return path


def resource_plan(config, available=None, cpu_count=None):
    local = config['local_cluster']
    available = psutil.virtual_memory().available if available is None else available
    cpus = max(1, cpu_count or psutil.cpu_count() or 1)
    budget = int(available * local['available_memory_fraction'])
    minimum = parse_bytes(local['minimum_worker_memory'])
    if budget < minimum:
        raise RuntimeError('Available memory is too low for one worker. Close other applications and retry.')
    threads = min(local['threads_per_worker'], cpus)
    workers = min(local['n_workers'], max(1, cpus // threads), budget // minimum)
    memory = min(parse_bytes(local['memory_limit']), budget // workers)
    return {
        'n_workers': int(workers), 'threads_per_worker': int(threads),
        'memory_limit_bytes': int(memory), 'available_memory_bytes': int(available),
        'total_worker_budget_bytes': int(workers * memory),
        'available_memory_fraction': local['available_memory_fraction'],
        'local_directory': str(ROOT / local['local_directory']),
    }


@contextmanager
def start_client(config, plan):
    scratch = Path(plan['local_directory'])
    scratch.mkdir(parents=True, exist_ok=True)
    settings = {f'distributed.worker.memory.{key}': value
                for key, value in config['distributed']['worker']['memory'].items()}
    with dask.config.set(settings):
        with LocalCluster(
            n_workers=plan['n_workers'], threads_per_worker=plan['threads_per_worker'],
            memory_limit=plan['memory_limit_bytes'], processes=True,
            local_directory=str(scratch), host='127.0.0.1', dashboard_address=None,
            silence_logs=40,
        ) as cluster:
            with Client(cluster) as client:
                client.wait_for_workers(plan['n_workers'], timeout=60)
                yield client


def inspect_worker(dask_worker=None):
    return {
        'pid': os.getpid(), 'rss_bytes': psutil.Process().memory_info().rss,
        'memory_limit_bytes': dask_worker.memory_manager.memory_limit,
        'threads': dask_worker.state.nthreads,
        'thresholds': {key: dask.config.get(f'distributed.worker.memory.{key}')
                       for key in ('target', 'spill', 'pause', 'terminate')},
    }


def read_sample(path, rows, encoding, columns):
    # Keep identifiers as strings, including leading zeros; use Arrow storage.
    return pd.read_csv(path, nrows=rows, encoding=encoding,
                       dtype={column: 'string[pyarrow]' for column in columns})
