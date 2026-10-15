"""Define typed preprocessing policies, datasets, and artifact evidence."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from user_behavior_analysis.models.cleaning_models import FileEvidence


@dataclass(frozen=True)
class PreprocessingPolicy:
    """Control bounded encoding and comparable read measurements.

    Attributes:
        batch_rows: Maximum decoded input records in a batch.
        row_group_rows: Maximum rows per output Parquet row group.
        compression_level: Zstandard compression level.
        dictionary_category_limit: Maximum categories collected for shared encoding.
        benchmark_repeats: Alternating full-read repetitions per layout.
        policy_version: Identifier for preprocessing semantics.
    """

    batch_rows: int
    row_group_rows: int
    compression_level: int
    dictionary_category_limit: int
    benchmark_repeats: int
    policy_version: str


@dataclass(frozen=True)
class PreprocessingRequest:
    """Designate the verified source catalog and isolated output paths.

    Attributes:
        source_catalog: Existing cleaned-dataset catalog.
        output_dir: New project-confined processed-data directory.
        report_dir: Evidence destination.
        policy: Explicit encoding and benchmark settings.
    """

    source_catalog: Path
    output_dir: Path
    report_dir: Path
    policy: PreprocessingPolicy


@dataclass(frozen=True)
class SourceDataset:
    """Describe a content-verified source relation.

    Attributes:
        catalog_path: Verified catalog location.
        catalog_sha256: Catalog content fingerprint.
        directory: Declared dataset directory.
        parts: Content-verified data parts in deterministic order.
        rows: Declared and independently counted physical rows.
    """

    catalog_path: Path
    catalog_sha256: str
    directory: Path
    parts: list[Path]
    rows: int


@dataclass(frozen=True)
class EncodingPlan:
    """Describe safe integer widths and optional category dictionary.

    Attributes:
        event_id_bits: Unsigned lineage-record width, selected from observed range.
        categories: Complete sorted source categories or None for bounded fallback.
        maximum_event_id: Largest observed source-record ordinal.
    """

    event_id_bits: int
    categories: tuple[str, ...] | None
    maximum_event_id: int


@dataclass(frozen=True)
class EncodedEvents:
    """Describe encoded events and their equivalent benchmark CSV.

    Attributes:
        paths: Ordered encoded event parts.
        rows: Source events processed.
        value_sha256: Canonical source value fingerprint.
        behaviors: Source counts for each behavior.
        peak_rss_bytes: Sampled driver RSS.
        csv_path: Equivalent CSV benchmark input.
    """

    paths: list[Path]
    rows: int
    value_sha256: str
    behaviors: dict[str, int]
    peak_rss_bytes: int
    csv_path: Path


class AggregateEvidence(TypedDict):
    """Record persisted aggregate keys and exact event-count conservation."""

    name: str
    keys: list[str]
    rows: int
    event_count: int
    behavior_counts: dict[str, int]
    columns: list[str]
    files: list[str]


class ReadTrial(TypedDict):
    """Describe one complete Arrow decode using the same columns and rows."""

    layout: str
    repeat: int
    rows: int
    seconds: float
    observed_driver_peak_rss_bytes: int


class PreprocessingReport(TypedDict):
    """Combine encoding, aggregate, performance, and file-integrity evidence."""

    status: str
    checked_at_utc: str
    code_commit: str
    source_catalog_path: str
    source_catalog_sha256: str
    source_rows: int
    output_rows: int
    input_value_sha256: str
    output_value_sha256: str
    values_match: bool
    policy_version: str
    policy_sha256: str
    event_id_bits: int
    dictionary_category_count: int | None
    output_schema: dict[str, str]
    aggregates: list[AggregateEvidence]
    files: list[FileEvidence]
    read_trials: list[ReadTrial]
    source_event_bytes: int
    output_event_bytes: int
    benchmark_csv_bytes: int
    observed_driver_peak_rss_bytes: int
    elapsed_seconds: float
