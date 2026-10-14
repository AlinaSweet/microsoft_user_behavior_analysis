"""Measure bounded CSV reads without claiming full-file performance."""

import gc
import hashlib
import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import dask.dataframe as dd
import pandas as pd
import psutil
from dask.utils import parse_bytes
from distributed import Client

from user_behavior_analysis.common.constants import MEMORY_SAMPLE_INTERVAL_SECONDS
from user_behavior_analysis.common.constants import SAMPLE_TIMEOUT_SECONDS
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.dao.source_repository import read_sample
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.models.report_models import BenchmarkReport
from user_behavior_analysis.models.report_models import BenchmarkSummary
from user_behavior_analysis.models.report_models import BenchmarkTrial
from user_behavior_analysis.models.report_models import ResourcePlan
from user_behavior_analysis.models.report_models import WorkerState
from user_behavior_analysis.service.environment import package_versions
from user_behavior_analysis.service.runtime import inspect_worker
from user_behavior_analysis.service.runtime import resource_plan
from user_behavior_analysis.service.runtime import start_client


@dataclass(frozen=True)
class _TrialRequest:
    source: Path
    config: ProjectConfig
    plan: ResourcePlan
    rows: int
    block: str


def _worker_states(client: Client) -> dict[str, WorkerState]:
    return cast(dict[str, WorkerState], client.run(inspect_worker))


def _measure_trial(
    client: Client, request: _TrialRequest, repeat: int
) -> BenchmarkTrial:
    frame = dd.read_csv(
        str(request.source),
        blocksize=parse_bytes(request.block),
        encoding=request.config["data"]["encoding"],
        dtype={
            column: "string[pyarrow]" for column in request.config["data"]["columns"]
        },
    )
    peaks = {
        address: state["rss_bytes"] for address, state in _worker_states(client).items()
    }
    driver_peak = psutil.Process().memory_info().rss
    tick = time.perf_counter()
    future = client.compute(frame.head(request.rows, npartitions=1, compute=False))
    while not future.done():
        if time.perf_counter() > tick + SAMPLE_TIMEOUT_SECONDS:
            future.cancel()
            raise TimeoutError("Sample read exceeded its configured timeout")
        for address, state in _worker_states(client).items():
            peaks[address] = max(peaks.get(address, 0), state["rss_bytes"])
        driver_peak = max(driver_peak, psutil.Process().memory_info().rss)
        time.sleep(MEMORY_SAMPLE_INTERVAL_SECONDS)
    sample = cast(pd.DataFrame, future.result(timeout=5))
    elapsed = time.perf_counter() - tick
    for address, state in _worker_states(client).items():
        peaks[address] = max(peaks.get(address, 0), state["rss_bytes"])
    if len(sample) != request.rows:
        raise ValueError("First CSV partition has fewer rows than the requested sample")
    result: BenchmarkTrial = {
        "block_size": request.block,
        "repeat": repeat + 1,
        "returned_sample_rows": len(sample),
        "csv_partition_count": frame.npartitions,
        "wall_seconds": round(elapsed, 4),
        "sample_memory_bytes": int(sample.memory_usage(deep=True).sum()),
        "observed_worker_peak_rss_bytes": max(peaks.values()),
        "observed_driver_peak_rss_bytes": driver_peak,
        "worker_peak_fraction": round(
            max(peaks.values()) / request.plan["memory_limit_bytes"], 4
        ),
        "status": "passed",
    }
    del sample, future, frame
    client.run(gc.collect)
    return result


def _summarize(
    trials: list[BenchmarkTrial], blocks: list[str]
) -> list[BenchmarkSummary]:
    summaries: list[BenchmarkSummary] = []
    for block in blocks:
        group = [trial for trial in trials if trial["block_size"] == block]
        summaries.append(
            {
                "block_size": block,
                "median_wall_seconds": round(
                    statistics.median(item["wall_seconds"] for item in group), 4
                ),
                "max_observed_worker_rss_bytes": max(
                    item["observed_worker_peak_rss_bytes"] for item in group
                ),
                "max_worker_peak_fraction": max(
                    item["worker_peak_fraction"] for item in group
                ),
            }
        )
    return summaries


def benchmark_source(
    config: ProjectConfig,
    source: Path,
    rows: int | None = None,
    repeats: int | None = None,
) -> BenchmarkReport:
    """Measure actual worker behavior on bounded source partitions.

    Args:
        config: Validated resource and benchmark settings.
        source: Existing CSV source file.
        rows: Optional number of returned sample rows.
        repeats: Optional measurement count per block size.

    Returns:
        Benchmark evidence; existing reports and catalog files are untouched.

    Raises:
        ValueError: Parameters or the first partition cannot satisfy the sample.
        RuntimeError: A worker restarts during measurement.
        TimeoutError: A trial exceeds its bounded timeout.

    Notes:
        Starts workers and uses project-local scratch storage.
    """
    sample_rows = config["benchmark"]["sample_rows"] if rows is None else rows
    repeat_count = config["benchmark"]["repeats"] if repeats is None else repeats
    if sample_rows <= 0 or repeat_count <= 0:
        raise ValueError("Sample rows and repeats must be positive")
    plan = resource_plan(config)
    blocks = list(
        dict.fromkeys(
            [
                config["local_cluster"]["csv_blocksize"],
                *config["benchmark"]["block_sizes"],
            ]
        )
    )
    trials: list[BenchmarkTrial] = []
    started = time.perf_counter()
    with start_client(config, plan) as client:
        client.submit(
            read_sample,
            source,
            1000,
            config["data"]["encoding"],
            config["data"]["columns"],
        ).result(timeout=90)
        client.run(gc.collect)
        initial_pids = {state["pid"] for state in _worker_states(client).values()}
        for repeat in range(repeat_count):
            order = blocks if repeat % 2 == 0 else list(reversed(blocks))
            for block in order:
                request = _TrialRequest(source, config, plan, sample_rows, block)
                trials.append(_measure_trial(client, request, repeat))
        final_pids = {state["pid"] for state in _worker_states(client).values()}
        if initial_pids != final_pids:
            raise RuntimeError("A worker restarted during the sample benchmark")
    canonical_config = json.dumps(config, sort_keys=True).encode("utf-8")
    return {
        "status": "passed",
        "checked_at_utc": utc_timestamp(),
        "scope": "First CSV partition; bounded sample, not full-file performance.",
        "sample_rows": sample_rows,
        "repeats": repeat_count,
        "resource_plan": plan,
        "configured_block_size": config["local_cluster"]["csv_blocksize"],
        "config_sha256": hashlib.sha256(canonical_config).hexdigest(),
        "config_hash_scope": "Effective configuration serialized as sorted JSON",
        "source_sha256": sha256_file(source),
        "packages": package_versions(),
        "worker_restart_count": 0,
        "monitoring": "RSS sampled every 0.1 seconds; brief peaks may be missed.",
        "cluster_and_trials_seconds": round(time.perf_counter() - started, 4),
        "summary": _summarize(trials, blocks),
        "trials": trials,
    }
