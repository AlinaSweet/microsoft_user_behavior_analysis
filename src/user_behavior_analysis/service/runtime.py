"""Plan and manage Dask workers with explicitly applied resource settings."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import dask
import psutil
from dask.utils import parse_bytes
from distributed import Client
from distributed import LocalCluster
from distributed import Worker

from user_behavior_analysis.common.constants import MEMORY_THRESHOLD_KEYS
from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.exceptions import ResourceError
from user_behavior_analysis.models.config_models import MemoryThresholds
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.models.report_models import ResourcePlan
from user_behavior_analysis.models.report_models import WorkerState


def resource_plan(
    config: ProjectConfig, available: int | None = None, cpu_count: int | None = None
) -> ResourcePlan:
    """Plan workers within the current available-memory budget.

    Args:
        config: Validated cluster settings.
        available: Optional available RAM in bytes for deterministic planning.
        cpu_count: Optional available logical CPU count.

    Returns:
        The effective worker count, memory limits, and scratch path.

    Raises:
        ResourceError: Available memory cannot support the minimum worker.
    """
    local = config["local_cluster"]
    available = psutil.virtual_memory().available if available is None else available
    cpus = max(1, cpu_count or psutil.cpu_count() or 1)
    budget = int(available * local["available_memory_fraction"])
    minimum = parse_bytes(local["minimum_worker_memory"])
    if budget < minimum:
        raise ResourceError(
            "Available memory is too low; close other applications and retry."
        )
    threads = min(local["threads_per_worker"], cpus)
    workers = min(local["n_workers"], max(1, cpus // threads), budget // minimum)
    memory = min(parse_bytes(local["memory_limit"]), budget // workers)
    return {
        "n_workers": int(workers),
        "threads_per_worker": int(threads),
        "memory_limit_bytes": int(memory),
        "available_memory_bytes": int(available),
        "total_worker_budget_bytes": int(workers * memory),
        "available_memory_fraction": local["available_memory_fraction"],
        "local_directory": str(PROJECT_ROOT / local["local_directory"]),
    }


@contextmanager
def start_client(config: ProjectConfig, plan: ResourcePlan) -> Iterator[Client]:
    """Start a managed local cluster with the configured memory rules.

    Args:
        config: Validated Dask thresholds and resource settings.
        plan: Effective worker budget.

    Yields:
        A client connected to independently managed local worker processes.

    Notes:
        Creates project-local scratch storage and closes workers on exit.
    """
    scratch = Path(plan["local_directory"])
    scratch.mkdir(parents=True, exist_ok=True)
    settings = {
        f"distributed.worker.memory.{key}": value
        for key, value in config["distributed"]["worker"]["memory"].items()
    }
    with dask.config.set(settings):
        with LocalCluster(
            n_workers=plan["n_workers"],
            threads_per_worker=plan["threads_per_worker"],
            memory_limit=plan["memory_limit_bytes"],
            processes=True,
            local_directory=str(scratch),
            host="127.0.0.1",
            dashboard_address=None,
            silence_logs=40,
        ) as cluster:
            with Client(cluster) as client:
                client.wait_for_workers(plan["n_workers"], timeout=60)
                yield client


def inspect_worker(dask_worker: Worker | None = None) -> WorkerState:
    """Inspect an actual worker through Dask's callback injection.

    Args:
        dask_worker: Worker supplied by Client.run, not a caller-created worker.

    Returns:
        Process memory, thread count, limit, and active thresholds.

    Raises:
        ValueError: No worker is supplied.
        ResourceError: The worker has no configured memory limit.
    """
    if dask_worker is None:
        raise ValueError("Dask must supply the worker instance")
    memory_limit = dask_worker.memory_manager.memory_limit
    if memory_limit is None:
        raise ResourceError("Worker memory limit is not configured")
    return {
        "pid": os.getpid(),
        "rss_bytes": psutil.Process().memory_info().rss,
        "memory_limit_bytes": memory_limit,
        "threads": dask_worker.state.nthreads,
        "thresholds": cast(
            MemoryThresholds,
            {
                key: dask.config.get(f"distributed.worker.memory.{key}")
                for key in MEMORY_THRESHOLD_KEYS
            },
        ),
    }
