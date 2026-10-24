"""Define normalized database construction and query evidence records."""

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

SqlValue = str | int | float | bytes | None


@dataclass(frozen=True)
class DatabaseRequest:
    """Describe a new database and its bounded registered input.

    Attributes:
        catalog: Registered validated-record Parquet input.
        database: New project-local SQLite destination.
        report_dir: Build and integrity report directory.
        batch_rows: Maximum source records imported at once.
    """

    catalog: Path
    database: Path
    report_dir: Path
    batch_rows: int = 100000


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
    diagnostics_sha256: str
    policy_sha256: str
    batch_rows: int
    elapsed_seconds: float
    observed_driver_peak_rss_bytes: int
