"""Serialize fixed dashboard aggregate queries with explicit missing results."""

from typing import Any
from typing import cast

import duckdb
import pandas as pd


def aggregate_records(
    connection: duckdb.DuckDBPyConnection, query: str
) -> list[dict[str, Any]]:
    """Serialize a fixed aggregate query without converting unavailable ratios to zero.

    Args:
        connection: Registered source and filtered tables.
        query: Fixed analytical SQL; no request text is interpolated.

    Returns:
        JSON-compatible records with nulls preserved.
    """
    frame = connection.execute(query).df()
    return cast(
        list[dict[str, Any]],
        frame.astype(object).where(pd.notna(frame), None).to_dict("records"),
    )
