"""Expose a read-only parameterized SQLite-to-Pandas query interface."""

import sqlite3
from collections.abc import Generator
from contextlib import closing
from pathlib import Path
from typing import cast

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.local_cache import configure_sqlite_cache
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.database_models import SqlValue

QUERY_NAMES = (
    "overview",
    "behavior_distribution",
    "daily_active",
    "weekly_active",
    "popular_items",
    "popular_categories",
    "user_sequences",
    "funnel_reach",
    "strict_funnel",
    "user_proxy_segments",
    "item_repurchase",
)


def query_path(name: str) -> Path:
    """Resolve one explicitly registered SQL query.

    Args:
        name: Query name from the fixed project registry.

    Returns:
        Existing project-confined SQL source.

    Raises:
        ValueError: The query name is not registered.
    """
    if name not in QUERY_NAMES:
        raise ValueError(f"Unregistered SQL query: {name}")
    return input_file_path(PROJECT_ROOT / "sql/queries" / (name + ".sql"))


class SQLiteClient:
    """Read project databases without allowing source mutation or unbounded frames."""

    def __init__(self, database: Path | str) -> None:
        """Validate an existing project-confined database.

        Args:
            database: Existing SQLite file.
        """
        self.database = input_file_path(project_output_path(database))

    def iter_frames(
        self,
        sql: str,
        parameters: dict[str, SqlValue] | None = None,
        chunk_rows: int = 50000,
    ) -> Generator[pd.DataFrame, None, None]:
        """Stream a parameterized query as bounded Pandas frames.

        Args:
            sql: A single SQL read statement.
            parameters: Named bound values, never interpolated into SQL text.
            chunk_rows: Positive maximum rows in each returned frame.

        Yields:
            Query frames, preserving text identifiers and nullable SQL values.

        Raises:
            ValueError: The requested chunk size is invalid.
            pd.errors.DatabaseError: SQLite rejects the statement.

        Notes:
            Closes the read-only connection when exhausted or the generator closes.
        """
        if chunk_rows <= 0:
            raise ValueError("Query chunk_rows must be positive")
        uri = self.database.as_uri() + "?mode=ro"
        configure_sqlite_cache()
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA query_only = ON")
            connection.execute("PRAGMA cache_size = -65536")
            connection.execute("PRAGMA temp_store = FILE")
            frames = pd.read_sql_query(
                sql, connection, params=parameters, chunksize=chunk_rows
            )
            yield from cast(Generator[pd.DataFrame, None, None], frames)

    def query_frame(
        self,
        sql: str,
        parameters: dict[str, SqlValue] | None = None,
        max_rows: int = 100000,
    ) -> pd.DataFrame:
        """Return a small DataFrame and reject results exceeding its row budget.

        Args:
            sql: A single SQL read statement.
            parameters: Named bound values.
            max_rows: Maximum total permitted output rows.

        Returns:
            Complete small query result.

        Raises:
            ValueError: The result or requested limit exceeds the contract.
        """
        if max_rows <= 0:
            raise ValueError("Query max_rows must be positive")
        frames = self.iter_frames(sql, parameters, max_rows + 1)
        try:
            frame = next(frames, pd.DataFrame())
        finally:
            frames.close()
        if len(frame) > max_rows:
            raise ValueError("Use iter_frames for query results exceeding max_rows")
        return frame
