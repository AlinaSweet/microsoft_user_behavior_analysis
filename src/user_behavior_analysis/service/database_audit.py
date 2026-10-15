"""Verify complete SQLite/source values and SQL exports through native row reads."""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TypedDict
from typing import cast

import pyarrow as pa  # type: ignore[import-untyped]  # No Arrow stubs.
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # No Arrow stubs.

from user_behavior_analysis.common.sqlite_runtime import (
    configure_sqlite_temporary_storage,
)
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.dao.dataset_repository import EVENT_COLUMNS
from user_behavior_analysis.dao.dataset_repository import load_dataset_catalog
from user_behavior_analysis.dao.sqlite_client import query_path
from user_behavior_analysis.models.database_models import DatabaseAnalysisReport
from user_behavior_analysis.models.database_models import SqlValue

LOGGER = logging.getLogger(__name__)

NativeRow = tuple[object, ...]


class RowComparison(TypedDict):
    """Record a complete native-row versus Arrow comparison."""

    name: str
    status: str
    rows: int
    mismatched_rows: int
    checks: dict[str, bool]


@contextmanager
def _read_connection(database: Path) -> Iterator[sqlite3.Connection]:
    path = input_file_path(project_output_path(database))
    configure_sqlite_temporary_storage()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA cache_size = -65536")
        connection.execute("PRAGMA temp_store = FILE")
        yield connection
    finally:
        connection.close()


def _arrow_rows(batch: pa.RecordBatch) -> list[NativeRow]:
    return list(zip(*(column.to_pylist() for column in batch.columns)))


def _differences(expected: list[NativeRow], actual: list[NativeRow]) -> int:
    return abs(len(expected) - len(actual)) + sum(
        left != right for left, right in zip(expected, actual)
    )


def audit_database_values(
    catalog: Path | str, database: Path | str, batch_rows: int = 20000
) -> RowComparison:
    """Compare every source cell with a native SQL join, without Pandas hashing.

    Args:
        catalog: Content-registered canonical input dataset.
        database: Complete normalized SQLite database.
        batch_rows: Positive Arrow and native-cursor batch limit.

    Returns:
        Whole-relation equality, integrity and foreign-key evidence.
    """
    if not 1 <= batch_rows <= 100000:
        raise ValueError("Audit batch_rows must lie between 1 and 100000")
    source = load_dataset_catalog(catalog)
    rows = 0
    mismatches = 0
    with _read_connection(Path(database)) as connection:
        cursor = connection.execute(
            "SELECT b.event_id, b.user_id, b.item_id, i.category_id, "
            + "b.behavior_type, b.event_time FROM behaviors b "
            + "JOIN items i ON i.item_id = b.item_id ORDER BY b.event_id"
        )
        for path in source.parts:
            for batch in pq.ParquetFile(path).iter_batches(
                batch_size=batch_rows, columns=EVENT_COLUMNS
            ):
                expected: list[NativeRow] = [
                    (
                        int(cast(int, row[0])),
                        row[1],
                        row[2],
                        row[3],
                        int(cast(int, row[4])),
                        cast(datetime, row[5]).strftime("%Y-%m-%d %H:%M:%S"),
                    )
                    for row in _arrow_rows(batch)
                ]
                mismatches += _differences(expected, cursor.fetchmany(len(expected)))
                rows += len(expected)
        no_extra_rows = cursor.fetchone() is None
        intact = connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        valid_references = (
            connection.execute("PRAGMA foreign_key_check").fetchone() is None
        )
    checks = {
        "source_row_count": rows == source.rows,
        "every_source_value": mismatches == 0,
        "no_extra_database_rows": no_extra_rows,
        "sqlite_integrity": intact,
        "foreign_keys": valid_references,
    }
    return {
        "name": "canonical_source_to_database",
        "status": "passed" if all(checks.values()) else "failed",
        "rows": rows,
        "mismatched_rows": mismatches,
        "checks": checks,
    }


def audit_query_exports(
    database: Path | str, report: DatabaseAnalysisReport
) -> list[RowComparison]:
    """Read back every exported SQL result and compare all native cursor values.

    Args:
        database: Verified normalized database.
        report: Complete query manifests and bound observation window.

    Returns:
        Per-query file, schema, row-count and every-value comparisons.

    Notes:
        This independently verifies serialization using Arrow/native cursors.
        Business semantics are additionally covered by known-outcome fixtures.
    """
    parameters: dict[str, SqlValue] = {
        "start_time": report["start_time"],
        "end_time": report["end_time_exclusive"],
        "window_days": report["window_days"],
        "limit": 50,
    }
    results: list[RowComparison] = []
    with _read_connection(Path(database)) as connection:
        for query in report["queries"]:
            name = query["name"]
            LOGGER.info("Auditing every exported SQL value: %s", name)
            cursor = connection.execute(
                query_path(name).read_text(encoding="utf-8"), parameters
            )
            columns = [description[0] for description in cursor.description]
            paths = [
                project_output_path(str(entry["path"])) for entry in query["files"]
            ]
            files_match = all(
                path.stat().st_size == int(entry["size_bytes"])
                and sha256_file(path) == entry["sha256"]
                for path, entry in zip(paths, query["files"])
            )
            inventory = (
                bool(paths)
                and len({path.parent for path in paths}) == 1
                and set(paths) == set(paths[0].parent.glob("*.parquet"))
            )
            rows = 0
            mismatches = 0
            same_schema = columns == query["columns"]
            for path in paths:
                for batch in pq.ParquetFile(path).iter_batches(batch_size=20000):
                    same_schema &= batch.schema.names == columns
                    expected = _arrow_rows(batch)
                    mismatches += _differences(
                        expected, cursor.fetchmany(len(expected))
                    )
                    rows += len(expected)
            checks = {
                "file_fingerprints": files_match,
                "complete_inventory": inventory,
                "schema": bool(same_schema),
                "row_count": rows == query["rows"],
                "every_exported_value": mismatches == 0,
                "no_extra_query_rows": cursor.fetchone() is None,
            }
            results.append(
                {
                    "name": name,
                    "status": "passed" if all(checks.values()) else "failed",
                    "rows": rows,
                    "mismatched_rows": mismatches,
                    "checks": checks,
                }
            )
    return results
