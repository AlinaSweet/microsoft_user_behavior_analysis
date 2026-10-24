"""Build bounded disk-backed user, item, and time aggregate relations."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]  # No Arrow stubs.

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.dataset_repository import write_encoded_table
from user_behavior_analysis.models.preprocessing_models import AggregateEvidence
from user_behavior_analysis.models.preprocessing_models import PreprocessingPolicy

CREATE_STAGE = """
CREATE TABLE events (
  event_id INTEGER PRIMARY KEY,
  user_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  behavior_type INTEGER NOT NULL,
  event_time TEXT NOT NULL
)
"""
INSERT_STAGE = """
INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)
"""
USER_DAILY = """
SELECT user_id, SUBSTR(event_time, 1, 10) AS event_date,
       COUNT(*) AS event_count,
       SUM(behavior_type = 1) AS pv_count,
       SUM(behavior_type = 2) AS fav_count,
       SUM(behavior_type = 3) AS cart_count,
       SUM(behavior_type = 4) AS buy_count,
       COUNT(DISTINCT item_id) AS unique_items,
       MIN(event_time) AS first_event_time, MAX(event_time) AS last_event_time
FROM events GROUP BY user_id, SUBSTR(event_time, 1, 10)
"""
ITEM_DAILY = """
SELECT item_id, SUBSTR(event_time, 1, 10) AS event_date,
       COUNT(*) AS event_count,
       SUM(behavior_type = 1) AS pv_count,
       SUM(behavior_type = 2) AS fav_count,
       SUM(behavior_type = 3) AS cart_count,
       SUM(behavior_type = 4) AS buy_count,
       COUNT(DISTINCT user_id) AS unique_users,
       MIN(event_time) AS first_event_time, MAX(event_time) AS last_event_time
FROM events GROUP BY item_id, SUBSTR(event_time, 1, 10)
"""
TIME_HOURLY = """
SELECT event_time, COUNT(*) AS event_count,
       SUM(behavior_type = 1) AS pv_count,
       SUM(behavior_type = 2) AS fav_count,
       SUM(behavior_type = 3) AS cart_count,
       SUM(behavior_type = 4) AS buy_count,
       COUNT(DISTINCT user_id) AS unique_users,
       COUNT(DISTINCT item_id) AS unique_items
FROM events GROUP BY event_time
"""
AGGREGATE_DEFINITIONS = {
    "user_daily_stats": (USER_DAILY, ["user_id", "event_date"]),
    "item_daily_stats": (ITEM_DAILY, ["item_id", "event_date"]),
    "time_hourly_stats": (TIME_HOURLY, ["event_time"]),
}
COUNT_COLUMNS = {
    "event_count",
    "pv_count",
    "fav_count",
    "cart_count",
    "buy_count",
    "unique_users",
    "unique_items",
}
BEHAVIOR_COLUMNS = {
    "1": "pv_count",
    "2": "fav_count",
    "3": "cart_count",
    "4": "buy_count",
}


@contextmanager
def open_aggregate_database(path: Path) -> Iterator[sqlite3.Connection]:
    """Create a new bounded-cache aggregation database.

    Args:
        path: New project-confined database path.

    Yields:
        A connection whose temporary grouping work can spill to disk.

    Raises:
        FileExistsError: An older working database occupies the path.
    """
    output = project_output_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Aggregation database already exists: {output}")
    connection = sqlite3.connect(output)
    try:
        connection.execute("PRAGMA cache_size = -65536")
        connection.execute("PRAGMA temp_store = FILE")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(CREATE_STAGE)
        yield connection
    finally:
        connection.close()


def stage_event_batch(connection: sqlite3.Connection, frame: pd.DataFrame) -> None:
    """Insert one verified event batch for complete global grouping.

    Args:
        connection: Open preprocessing database.
        frame: Canonical event fields in declared column order.

    Notes:
        Commits a bounded parameterized transaction without changing the frame.
    """
    values = frame.copy()
    values["behavior_type"] = pd.to_numeric(values["behavior_type"]).astype("uint8")
    values["event_time"] = pd.to_datetime(values["event_time"]).dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    with connection:
        connection.executemany(INSERT_STAGE, values.itertuples(index=False, name=None))


def _aggregate_table(frame: pd.DataFrame, upper_bound: int) -> pa.Table:
    """Convert an aggregate batch to compact, explicitly typed Arrow arrays.

    Args:
        frame: Aggregate rows containing identifiers, counts, dates, and times.
        upper_bound: Maximum possible count, used to choose uint32 or uint64.

    Returns:
        An Arrow table preserving column order, with string identifiers,
        date32 dates, millisecond timestamps, and bounded unsigned counts.

    Raises:
        pa.ArrowInvalid: A value cannot be safely represented by its chosen type.
        ValueError: A date or timestamp cannot be parsed.
    """
    arrays = []
    count_type = pa.uint32() if upper_bound <= 2**32 - 1 else pa.uint64()
    for column in frame.columns:
        if column in COUNT_COLUMNS:
            values = pa.array(frame[column], type=count_type, safe=True)
        elif column == "event_date":
            values = pa.array(pd.to_datetime(frame[column]).dt.date, type=pa.date32())
        elif column.endswith("_time"):
            values = pa.array(pd.to_datetime(frame[column])).cast(
                pa.timestamp("ms"), safe=True
            )
        else:
            values = pa.array(frame[column], type=pa.string())
        arrays.append(values)
    return pa.Table.from_arrays(arrays, names=list(frame.columns))


def export_aggregates(
    connection: sqlite3.Connection,
    directory: Path,
    policy: PreprocessingPolicy,
    source_rows: int,
) -> list[AggregateEvidence]:
    """Export three complete global aggregates with bounded count widths.

    Args:
        connection: Database containing every verified source event.
        directory: Project-confined aggregate root.
        policy: Batch, row-group, and compression settings.
        source_rows: Safe upper bound for all count columns.

    Returns:
        Key definitions, exact conservation counts, and persisted table paths.

    Raises:
        ValueError: The destination escapes the project, no aggregate rows are
            exported, or an aggregate does not conserve the source event count.
        OSError: An aggregate output cannot be written.
    """
    output = project_output_path(directory)
    results: list[AggregateEvidence] = []
    for name, (query, keys) in AGGREGATE_DEFINITIONS.items():
        cursor = connection.execute(query)
        columns = [entry[0] for entry in cursor.description]
        row_count = 0
        event_count = 0
        behaviors = {code: 0 for code in BEHAVIOR_COLUMNS}
        paths: list[str] = []
        while rows := cursor.fetchmany(policy.batch_rows):
            frame = pd.DataFrame.from_records(rows, columns=columns)
            table = _aggregate_table(frame, source_rows)
            path = output / name / f"part_{len(paths):05d}.parquet"
            write_encoded_table(
                table, path, policy.row_group_rows, policy.compression_level
            )
            row_count += len(frame)
            event_count += int(frame["event_count"].sum())
            for code, column in BEHAVIOR_COLUMNS.items():
                behaviors[code] += int(frame[column].sum())
            paths.append(str(path))
        if not paths or event_count != source_rows:
            raise ValueError(f"Aggregate {name} does not conserve source events")
        results.append(
            {
                "name": name,
                "keys": keys,
                "rows": row_count,
                "event_count": event_count,
                "behavior_counts": behaviors,
                "columns": columns,
                "files": paths,
            }
        )
    return results
