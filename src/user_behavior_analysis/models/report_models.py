"""Typed schemas for runtime reports and data artifact manifests."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from user_behavior_analysis.models.config_models import MemoryThresholds


@dataclass(frozen=True)
class ArtifactRequest:
    """Describe an artifact registration request.

    Attributes:
        path: Input data path; contents are never copied into Git.
        name: Lowercase catalog identifier.
        kind: Raw, interim, or processed data category.
        recipe: Origin or reproducible generation command.
        share_location: Optional confirmed sharing location.
    """

    path: Path | str
    name: str
    kind: str
    recipe: str
    share_location: str | None = None


class ResourcePlan(TypedDict):
    """Record the effective worker budget and scratch location.

    Attributes:
        n_workers: Planned worker process count.
        threads_per_worker: Threads per worker.
        memory_limit_bytes: Per-worker memory budget.
        available_memory_bytes: Available memory at planning time.
        total_worker_budget_bytes: Combined worker budget.
        available_memory_fraction: Configured share of available memory.
        local_directory: Effective project-local scratch path.
    """

    n_workers: int
    threads_per_worker: int
    memory_limit_bytes: int
    available_memory_bytes: int
    total_worker_budget_bytes: int
    available_memory_fraction: float
    local_directory: str


class WorkerState(TypedDict):
    """Record actual worker process properties and applied thresholds.

    Attributes:
        pid: Observed operating-system process identifier.
        rss_bytes: Observed resident memory.
        memory_limit_bytes: Applied per-worker memory budget.
        threads: Applied worker thread count.
        thresholds: Applied memory action fractions.
    """

    pid: int
    rss_bytes: int
    memory_limit_bytes: int
    threads: int
    thresholds: MemoryThresholds


class GitFilesReport(TypedDict):
    """Record file-policy issues without hiding failures as zero issues.

    Attributes:
        tracked_file_count: Number of indexed files.
        small_file_limit_bytes: Project delivery file-size limit.
        issues: Explicit file-policy failures.
    """

    tracked_file_count: int
    small_file_limit_bytes: int
    issues: list[str]


class ArtifactManifest(TypedDict):
    """Describe content identity, origin, and actual distribution state.

    Attributes:
        name: Snake-case catalog identifier.
        kind: Raw, interim, or processed category.
        project_path: Logical source path without copying input.
        size_bytes: Source content size.
        sha256: Streaming content fingerprint.
        created_at_utc: Registration timestamp.
        reproduction_or_origin: Source description or generation command.
        share_location: Optional confirmed data-sharing location.
        distribution_status: Recorded distribution state.
        data_file_in_git: Actual indexed-file lookup result.
    """

    name: str
    kind: str
    project_path: str
    size_bytes: int
    sha256: str
    created_at_utc: str
    reproduction_or_origin: str
    share_location: str | None
    distribution_status: str
    data_file_in_git: bool


class VerificationReport(TypedDict):
    """Confirm an artifact matches its recorded content fingerprint.

    Attributes:
        status: Content verification outcome.
        sha256: Verified source fingerprint.
    """

    status: str
    sha256: str


class RegistrationReport(TypedDict):
    """Return the saved manifest path and registered metadata.

    Attributes:
        manifest: Saved catalog path.
        artifact: Registered content identity and provenance.
    """

    manifest: str
    artifact: ArtifactManifest


class EnvironmentReport(TypedDict):
    """Record environment, source, worker, and file-policy checks.

    Attributes:
        status: Environment verification outcome.
        checked_at_utc: Verification timestamp.
        python: Interpreter version.
        packages: Actual package versions.
        sample_rows: Number of rows returned.
        columns: Observed ordered columns.
        applied_csv_blocksize: Effective partition size.
        csv_partition_count: Source partition count.
        source_size_bytes: Input content size.
        source_is_local_symlink: Whether the logical source is a symlink.
        resource_plan: Effective allocation plan.
        actual_workers: Observed worker properties by address.
        git_files: Indexed-file policy results.
    """

    status: str
    checked_at_utc: str
    python: str
    packages: dict[str, str]
    sample_rows: int
    columns: list[str]
    applied_csv_blocksize: str
    csv_partition_count: int
    source_size_bytes: int
    source_is_local_symlink: bool
    resource_plan: ResourcePlan
    actual_workers: dict[str, WorkerState]
    git_files: GitFilesReport


class BenchmarkTrial(TypedDict):
    """Record one bounded CSV read and sampled process-memory observations.

    Attributes:
        block_size: CSV partition size for this trial.
        repeat: One-based trial iteration.
        returned_sample_rows: Number of returned rows.
        csv_partition_count: Source partition count.
        wall_seconds: Observed elapsed read time.
        sample_memory_bytes: Returned DataFrame memory footprint.
        observed_worker_peak_rss_bytes: Largest sampled worker RSS.
        observed_driver_peak_rss_bytes: Largest sampled driver RSS.
        worker_peak_fraction: Observed peak relative to the worker budget.
        status: Trial outcome.
    """

    block_size: str
    repeat: int
    returned_sample_rows: int
    csv_partition_count: int
    wall_seconds: float
    sample_memory_bytes: int
    observed_worker_peak_rss_bytes: int
    observed_driver_peak_rss_bytes: int
    worker_peak_fraction: float
    status: str


class BenchmarkSummary(TypedDict):
    """Summarize repeated measurements for one CSV block size.

    Attributes:
        block_size: Compared partition size.
        median_wall_seconds: Median observed read time.
        max_observed_worker_rss_bytes: Largest sampled worker RSS.
        max_worker_peak_fraction: Largest observed budget fraction.
    """

    block_size: str
    median_wall_seconds: float
    max_observed_worker_rss_bytes: int
    max_worker_peak_fraction: float


class BenchmarkReport(TypedDict):
    """Record the scope and reproducible evidence of a sample benchmark.

    Attributes:
        status: Measurement outcome.
        checked_at_utc: Measurement timestamp.
        scope: Bounded measurement scope.
        sample_rows: Requested returned rows per trial.
        repeats: Trials per partition size.
        resource_plan: Effective process and memory plan.
        configured_block_size: Default configured partition size.
        config_sha256: Fingerprint of the effective configuration.
        config_hash_scope: Configuration serialization convention.
        source_sha256: Fingerprint of input bytes.
        packages: Actual runtime versions.
        worker_restart_count: Detected restart count for a successful run.
        monitoring: Memory sampling scope and limitation.
        cluster_and_trials_seconds: Elapsed cluster and trial execution time.
        summary: Per-block aggregate observations.
        trials: Individual measurement records.
    """

    status: str
    checked_at_utc: str
    scope: str
    sample_rows: int
    repeats: int
    resource_plan: ResourcePlan
    configured_block_size: str
    config_sha256: str
    config_hash_scope: str
    source_sha256: str
    packages: dict[str, str]
    worker_restart_count: int
    monitoring: str
    cluster_and_trials_seconds: float
    summary: list[BenchmarkSummary]
    trials: list[BenchmarkTrial]
