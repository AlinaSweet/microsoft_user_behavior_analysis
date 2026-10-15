"""Construct third-normal-form SQLite relations with bounded parameterized batches."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
from pandas.api.types import is_integer_dtype

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.sqlite_runtime import (
    configure_sqlite_temporary_storage,
)
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.dataset_repository import EVENT_COLUMNS

SCHEMA_PATH = PROJECT_ROOT / "sql/schema.sql"
INDEXES_PATH = PROJECT_ROOT / "sql/indexes.sql"
TABLE_NAMES = (
    "behaviors",
    "users",
    "items",
    "categories",
    "event_times",
    "calendar_dates",
)


def create_database(path: Path) -> sqlite3.Connection:
    """Create a new bounded-cache database with active foreign keys.

    Args:
        path: New project-confined construction file.

    Returns:
        Connection owned by the caller, with the normalized schema initialized.

    Raises:
        FileExistsError: The destination already exists.
    """
    output = project_output_path(path)
    if output.exists():
        raise FileExistsError(f"Database destination already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    configure_sqlite_temporary_storage()
    connection = sqlite3.connect(output)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA cache_size = -65536")
    connection.execute("PRAGMA temp_store = FILE")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    connection.execute(
        "CREATE TEMP TABLE stage_events (event_id INTEGER NOT NULL, "
        + "user_id TEXT NOT NULL, item_id TEXT NOT NULL, category_id TEXT NOT NULL, "
        + "behavior_type INTEGER NOT NULL, event_time TEXT NOT NULL) STRICT"
    )
    return connection


def _batch_rows(frame: pd.DataFrame) -> Iterator[tuple[int, str, str, str, int, str]]:
    if frame.isna().any().any():
        raise ValueError("Database input contains missing required values")
    for column in ("event_id", "behavior_type"):
        if not is_integer_dtype(frame[column].dtype):
            raise ValueError(f"Database input requires integer {column}")
    if not frame["event_id"].between(1, 2**63 - 1).all():
        raise ValueError("Event IDs exceed the positive SQLite integer range")
    if not frame["behavior_type"].isin([1, 2, 3, 4]).all():
        raise ValueError("Unknown behavior code")
    for column in ("user_id", "item_id", "category_id"):
        if not frame[column].map(lambda value: isinstance(value, str)).all():
            raise ValueError(f"Identifiers must remain strings: {column}")
        identifier_text = frame[column].astype("string")
        if identifier_text.str.contains(r"[\s\x00-\x1f\x7f]", regex=True).any():
            raise ValueError(
                f"Identifiers contain whitespace or control characters: {column}"
            )
    times = pd.to_datetime(frame["event_time"])
    if times.dt.tz is not None or not times.eq(times.dt.floor("h")).all():
        raise ValueError("Source event times must be naive and hour-aligned")
    values = frame[EVENT_COLUMNS].copy()
    values["event_time"] = times.dt.strftime("%Y-%m-%d %H:%M:%S")
    for event, user, item, category, behavior, timestamp in values.itertuples(
        index=False, name=None
    ):
        yield int(event), str(user), str(item), str(category), int(behavior), str(
            timestamp
        )


def import_event_batch(connection: sqlite3.Connection, frame: pd.DataFrame) -> None:
    """Import one batch atomically while enforcing global entity consistency.

    Args:
        connection: Initialized database with foreign keys enabled.
        frame: Canonical six-column events with integer event and behavior codes.

    Raises:
        ValueError: A category changes for the same item or source types are unsafe.
        sqlite3.IntegrityError: A business key, ID or reference is invalid.
    """
    with connection:
        connection.execute("DELETE FROM stage_events")
        connection.executemany(
            "INSERT INTO stage_events VALUES (?, ?, ?, ?, ?, ?)", _batch_rows(frame)
        )
        connection.execute(
            "INSERT OR IGNORE INTO categories "
            + "SELECT DISTINCT category_id FROM stage_events"
        )
        connection.execute(
            "INSERT OR IGNORE INTO items SELECT DISTINCT item_id, category_id "
            + "FROM stage_events"
        )
        conflict = connection.execute(
            "SELECT 1 FROM stage_events s JOIN items i USING (item_id) "
            + "WHERE s.category_id <> i.category_id LIMIT 1"
        ).fetchone()
        if conflict is not None:
            raise ValueError(
                "One item maps to conflicting categories across input batches"
            )
        connection.execute(
            "INSERT OR IGNORE INTO users SELECT DISTINCT user_id FROM stage_events"
        )
        connection.execute(
            "INSERT OR IGNORE INTO calendar_dates "
            + "SELECT DISTINCT substr(event_time, 1, 10) FROM stage_events"
        )
        connection.execute(
            "INSERT OR IGNORE INTO event_times "
            + "SELECT DISTINCT event_time, substr(event_time, 1, 10) FROM stage_events"
        )
        connection.execute(
            "INSERT INTO behaviors SELECT event_id, user_id, item_id, behavior_type, "
            + "event_time FROM stage_events"
        )


def finish_database(
    connection: sqlite3.Connection, metadata: dict[str, str]
) -> dict[str, int]:
    """Create workload indexes and check the complete normalized database.

    Args:
        connection: Complete imported database.
        metadata: Parameterized source and generation provenance values.

    Returns:
        Exact persisted relation counts.

    Raises:
        RuntimeError: Integrity or foreign-key checks fail.
    """
    connection.executescript(INDEXES_PATH.read_text(encoding="utf-8"))
    with connection:
        connection.executemany(
            "INSERT INTO dataset_metadata VALUES (?, ?)", metadata.items()
        )
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("Database contains a foreign-key violation")
    integrity = connection.execute("PRAGMA integrity_check").fetchall()
    if integrity != [("ok",)]:
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    return {
        name: int(connection.execute("SELECT COUNT(*) FROM " + name).fetchone()[0])
        for name in TABLE_NAMES
    }
