"""Typed configuration contracts used by configuration and runtime services."""

from typing import TypedDict


class MemoryThresholds(TypedDict):
    """Define fractions controlling worker memory actions.

    Attributes:
        target: Managed-memory spill threshold.
        spill: Process-memory spill threshold.
        pause: Threshold stopping new tasks.
        terminate: Threshold restarting an overloaded worker.
    """

    target: float
    spill: float
    pause: float
    terminate: float


class WorkerSettings(TypedDict):
    """Group the worker memory configuration.

    Attributes:
        memory: Worker memory action thresholds.
    """

    memory: MemoryThresholds


class DistributedSettings(TypedDict):
    """Group the distributed worker configuration.

    Attributes:
        worker: Distributed worker settings.
    """

    worker: WorkerSettings


class ClusterSettings(TypedDict):
    """Define local worker limits and project scratch location.

    Attributes:
        n_workers: Maximum worker process count.
        threads_per_worker: Maximum threads per worker.
        memory_limit: Upper byte-size limit for each worker.
        csv_blocksize: CSV parsing partition size.
        available_memory_fraction: Share of available RAM for all workers.
        minimum_worker_memory: Minimum viable worker memory budget.
        local_directory: Project-local worker scratch directory.
    """

    n_workers: int
    threads_per_worker: int
    memory_limit: str
    csv_blocksize: str
    available_memory_fraction: float
    minimum_worker_memory: str
    local_directory: str


class SourceSettings(TypedDict):
    """Define the unchanged input CSV contract.

    Attributes:
        default_path: Default local CSV path.
        encoding: CSV text encoding.
        columns: Expected ordered CSV column names.
    """

    default_path: str
    encoding: str
    columns: list[str]


class BenchmarkSettings(TypedDict):
    """Define bounded sample measurement parameters.

    Attributes:
        sample_rows: Rows returned by each bounded trial.
        block_sizes: CSV partition sizes to compare.
        repeats: Trials per block size.
    """

    sample_rows: int
    block_sizes: list[str]
    repeats: int


class ProjectConfig(TypedDict):
    """Combine the complete configuration without untyped nested dictionaries.

    Attributes:
        distributed: Worker memory action thresholds.
        local_cluster: Local process and memory limits.
        data: Input CSV contract.
        benchmark: Bounded trial parameters.
    """

    distributed: DistributedSettings
    local_cluster: ClusterSettings
    data: SourceSettings
    benchmark: BenchmarkSettings
