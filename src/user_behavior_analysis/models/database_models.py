"""Define normalized database construction and query evidence records."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

SqlValue = str | int | float | bytes | None


@dataclass(frozen=True)
class DatabaseRequest:
    """Describe a new database and its bounded registered input."""

    catalog: Path
    database: Path
    report_dir: Path
    batch_rows: int = 100000


@dataclass(frozen=True)
class DatabaseAnalysisRequest:
    """Describe complete SQL exports from a content-verified build report."""

    database_report: Path
    output_dir: Path
    report_dir: Path
    window_days: int = 7
    chunk_rows: int = 50000


class IndexTrial(TypedDict):
    """Record an observed indexed or full-scan count query."""

    lookup: str
    mode: str
    repeat: int
    rows_matched: int
    seconds: float


class DatabaseReport(TypedDict):
    """Record complete source-to-database verification and resource observations."""

    status: str
    checked_at_utc: str
    code_commit: str
    source_catalog: str
    source_catalog_sha256: str
    database_path: str
    database_sha256: str
    database_size_bytes: int
    source_rows: int
    loaded_rows: int
    source_value_sha256: str
    database_value_sha256: str
    counts: dict[str, int]
    checks: dict[str, bool]
    sqlite_version: str
    schema_sha256: str
    indexes_sha256: str
    batch_rows: int
    elapsed_seconds: float
    observed_driver_peak_rss_bytes: int


class QueryEvidence(TypedDict):
    """Record one complete bounded query export."""

    name: str
    rows: int
    columns: list[str]
    elapsed_seconds: float
    files: list[dict[str, str | int]]


class DatabaseAnalysisReport(TypedDict):
    """Record full SQL analysis exports, small summaries and query plans."""

    status: str
    checked_at_utc: str
    code_commit: str
    database_path: str
    database_sha256: str
    start_time: str
    end_time_exclusive: str
    window_days: int
    query_sha256: dict[str, str]
    queries: list[QueryEvidence]
    summaries: dict[str, list[dict[str, object]]]
    query_plans: dict[str, list[str]]
    index_trials: list[IndexTrial]
    checks: dict[str, bool]
