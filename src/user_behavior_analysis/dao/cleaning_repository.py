"""Persist global disk-backed deduplication and bounded Parquet exports."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.cleaning_models import RowAccounting

CREATE_EVENTS = """
CREATE TABLE events (
    event_id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    behavior_type TEXT NOT NULL,
    event_time TEXT NOT NULL,
    occurrences INTEGER NOT NULL DEFAULT 1,
    category_conflict INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, item_id, behavior_type, event_time)
)
"""
INSERT_EVENT = """
INSERT INTO events (
    event_id, user_id, item_id, category_id, behavior_type, event_time
) VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(user_id, item_id, behavior_type, event_time) DO UPDATE SET
    occurrences = events.occurrences + 1,
    category_conflict = MAX(
        events.category_conflict, events.category_id <> excluded.category_id
    )
"""
CLEAN_EVENTS = """
SELECT event_id, user_id, item_id, category_id, behavior_type, event_time
FROM events WHERE category_conflict = 0 ORDER BY event_id
"""
CONFLICTING_KEYS = """
SELECT event_id, user_id, item_id, category_id AS first_category_id,
       behavior_type, event_time, occurrences
FROM events WHERE category_conflict = 1
"""


@contextmanager
def open_cleaning_database(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a new bounded-cache database for global key reconciliation.

    Args:
        path: New project-confined SQLite path.

    Yields:
        A transaction-capable connection with disk-backed temporary storage.

    Raises:
        FileExistsError: A previous database already occupies the path.

    Notes:
        Creates the parent directory and a new SQLite database.
    """
    output = project_output_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Cleaning database already exists: {output}")
    connection = sqlite3.connect(output)
    try:
        connection.execute("PRAGMA cache_size = -65536")
        connection.execute("PRAGMA temp_store = FILE")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(CREATE_EVENTS)
        yield connection
    finally:
        connection.close()


def ingest_partition(connection: sqlite3.Connection, path: Path) -> None:
    """Merge one validated partition into the exact global key relation.

    Args:
        connection: Open cleaning database.
        path: Validated Parquet partition in source-record order.

    Notes:
        Commits one bounded transaction. Conflicting category values mark the
        entire duplicate key as quarantined, preserving all validated inputs.
    """
    frame = pd.read_parquet(path)
    frame["event_time"] = frame["event_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    with connection:
        connection.executemany(INSERT_EVENT, frame.itertuples(index=False, name=None))


def row_accounting(
    connection: sqlite3.Connection, input_rows: int, invalid_rows: int
) -> RowAccounting:
    """Reconcile input, rejected, duplicate, conflicting, and retained records.

    Args:
        connection: Fully ingested global event relation.
        input_rows: Number of parsed source data records.
        invalid_rows: Number of records failing source validation.

    Returns:
        Mutually exclusive row counts and an exact reconciliation flag.
    """
    clean, duplicates, conflict_rows, conflict_keys = connection.execute("""
        SELECT
          COALESCE(SUM(category_conflict = 0), 0),
          COALESCE(SUM(CASE WHEN category_conflict = 0
                           THEN occurrences - 1 ELSE 0 END), 0),
          COALESCE(SUM(CASE WHEN category_conflict = 1
                           THEN occurrences ELSE 0 END), 0),
          COALESCE(SUM(category_conflict = 1), 0)
        FROM events
        """).fetchone()
    return {
        "input_rows": input_rows,
        "invalid_rows": invalid_rows,
        "valid_before_deduplication": input_rows - invalid_rows,
        "duplicate_rows_removed": int(duplicates),
        "conflicting_rows_quarantined": int(conflict_rows),
        "conflicting_keys": int(conflict_keys),
        "clean_rows": int(clean),
        "reconciled": input_rows == invalid_rows + clean + duplicates + conflict_rows,
    }


def export_query(
    connection: sqlite3.Connection,
    query: str,
    directory: Path,
    batch_rows: int,
    parameters: tuple[object, ...] = (),
) -> list[Path]:
    """Stream a trusted internal query into bounded Parquet parts.

    Args:
        connection: Open database with a completed source relation.
        query: Internal constant SQL with no interpolated external values.
        directory: Project-confined destination directory.
        batch_rows: Maximum exported rows per file.
        parameters: Bound SQL values, never interpolated into query text.

    Returns:
        Ordered paths, including a schema-bearing empty part for empty results.

    Raises:
        ValueError: The requested batch size is not positive.

    Notes:
        Creates new Parquet files; query values must be parameterized by callers
        that introduce filters with external values.
    """
    if batch_rows <= 0:
        raise ValueError("Export batch size must be positive")
    output = project_output_path(directory)
    output.mkdir(parents=True, exist_ok=True)
    cursor = connection.execute(query, parameters)
    columns = [entry[0] for entry in cursor.description]
    paths: list[Path] = []
    while True:
        rows = cursor.fetchmany(batch_rows)
        if not rows and paths:
            break
        frame = pd.DataFrame.from_records(rows, columns=columns)
        if "event_time" in frame:
            frame["event_time"] = pd.to_datetime(frame["event_time"])
        for column in (
            "user_id",
            "item_id",
            "category_id",
            "behavior_type",
            "first_category_id",
        ):
            if column in frame:
                frame[column] = frame[column].astype("string[pyarrow]")
        if "event_id" in frame:
            frame["event_id"] = frame["event_id"].astype("int64")
        path = output / f"part_{len(paths):05d}.parquet"
        frame.to_parquet(path, index=False, compression=None)
        paths.append(path)
        if not rows:
            break
    return paths
