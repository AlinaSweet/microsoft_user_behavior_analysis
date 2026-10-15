"""Define cleaning requests, partition evidence, and quality report contracts."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from user_behavior_analysis.models.report_models import ResourcePlan


@dataclass(frozen=True)
class CleaningPolicy:
    """Define bounded processing and source-time validity rules.

    Attributes:
        chunk_rows: Maximum CSV records held in a parsing chunk.
        export_rows: Maximum records in an exported Parquet part.
        minimum_event_time: Optional inclusive source-time lower boundary.
        maximum_event_time: Exclusive source-time upper boundary.
        allowed_behaviors: Valid behavior codes from the task specification.
        policy_version: Identifier for documented cleaning semantics.
    """

    chunk_rows: int
    export_rows: int
    minimum_event_time: str | None
    maximum_event_time: str
    allowed_behaviors: tuple[str, ...]
    policy_version: str


@dataclass(frozen=True)
class CleaningRequest:
    """Designate isolated data and report destinations.

    Attributes:
        output_dir: New project-confined data directory.
        report_dir: Project-confined evidence directory.
        policy: Explicit source validation and batching policy.
    """

    output_dir: Path
    report_dir: Path
    policy: CleaningPolicy


@dataclass(frozen=True)
class PartitionRequest:
    """Identify one deterministic CSV-record partition.

    Attributes:
        directory: Project-confined partition output directory.
        partition_id: Zero-based parsing partition identifier.
        first_record: One-based first data-record ordinal.
        policy: Shared validation policy.
    """

    directory: Path
    partition_id: int
    first_record: int
    policy: CleaningPolicy


class PartitionEvidence(TypedDict):
    """Record bounded input validation results and their disk locations."""

    partition_id: int
    input_rows: int
    valid_rows: int
    invalid_rows: int
    violation_counts: dict[str, int]
    valid_path: str
    rejected_path: str | None


class RowAccounting(TypedDict):
    """Reconcile mutually exclusive input and output row categories."""

    input_rows: int
    invalid_rows: int
    valid_before_deduplication: int
    duplicate_rows_removed: int
    conflicting_rows_quarantined: int
    conflicting_keys: int
    clean_rows: int
    reconciled: bool


class DataProfile(TypedDict):
    """Record exact counts from the globally deduplicated event relation."""

    rows: int
    users: int
    items: int
    categories: int
    behavior_counts: dict[str, int]
    daily_counts: dict[str, int]
    minimum_event_time: str | None
    maximum_event_time: str | None
    items_with_multiple_categories: int
    duplicate_keys_remaining: int
    null_required_values: int


class AnomalyMetric(TypedDict):
    """Describe exact entity-count thresholds and non-destructive flags."""

    entity: str
    entities: int
    q1: float
    q3: float
    iqr_lower: float
    iqr_upper: float
    mean: float
    population_std: float
    sigma_lower: float
    sigma_upper: float
    iqr_flagged_entities: int
    sigma_flagged_entities: int
    action: str
    output_path: str


class FileEvidence(TypedDict):
    """Identify one generated dataset part by content."""

    path: str
    size_bytes: int
    sha256: str


class MemoryEvidence(TypedDict):
    """Report sampled process memory and observed worker identity changes."""

    driver_peak_rss_bytes: int
    worker_peak_rss_bytes: int
    worker_restart_count: int
    sampling: str


class ExportIntegrity(TypedDict):
    """Record canonical-value fingerprints independently read after export."""

    expected_rows: int
    exported_rows: int
    expected_value_sha256: str
    exported_value_sha256: str
    values_match: bool
    algorithm: str


class CleaningReport(TypedDict):
    """Combine input identity, cleaning results, resources, and artifact evidence."""

    status: str
    checked_at_utc: str
    policy_version: str
    policy_sha256: str
    source_path: str
    source_size_bytes: int
    source_sha256_before: str
    source_sha256_after: str
    code_commit: str
    output_dir: str
    row_accounting: RowAccounting
    profile: DataProfile
    output_integrity: ExportIntegrity
    anomalies: list[AnomalyMetric]
    partitions: list[PartitionEvidence]
    files: list[FileEvidence]
    resource_plan: ResourcePlan
    memory: MemoryEvidence
    wall_seconds: float
    provenance_status: str
