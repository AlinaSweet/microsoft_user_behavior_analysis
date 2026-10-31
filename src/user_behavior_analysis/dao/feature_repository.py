"""Provide confined feature paths and bounded DuckDB operations."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.feature_models import FeatureSettings


def load_feature_settings(path: Path) -> FeatureSettings:
    """Load and validate feature-system locations and resource bounds.

    Args:
        path: Project-relative configuration file.

    Returns:
        Validated paths and declared transformation parameters.

    Raises:
        ValueError: Windows, fit anchor or resource bounds are invalid.
    """
    raw = json.loads(
        input_file_path(project_output_path(path)).read_text(encoding="utf-8")
    )
    path_names = (
        "source_catalog",
        "source_database",
        "base_dir",
        "output_dir",
        "report_dir",
        "eda_report_dir",
    )
    paths = {name: project_output_path(Path(raw.pop(name))) for name in path_names}
    for name in ("source_catalog", "source_database"):
        input_file_path(paths[name])
    anchors = raw["anchors"]
    if not anchors or anchors != sorted(set(anchors)):
        raise ValueError("Anchors must be nonempty, ordered and distinct")
    for anchor in anchors:
        if date.fromisoformat(anchor).isoformat() != anchor:
            raise ValueError("Anchors must use ISO calendar dates")
    invalid = [
        raw["fit_anchor"] != min(anchors),
        raw["windows"] != [1, 3, 7, 30],
        raw["candidate_days"] != 7,
        raw["label_days"] != 7,
        not 256 <= raw["memory_mb"] <= 2048,
        not 1 <= raw["threads"] <= 4,
        not 1 <= raw["svd_components"] <= 64,
        not 1 <= raw["sequence_length"] <= 500,
        not 1 <= raw["cooccurrence_max_items"] <= 5000,
        raw["cooccurrence_min_users"] < 2,
        raw["cooccurrence_neighbors"] < 1,
        list(raw["behavior_weights"]) != ["pv", "fav", "cart", "buy"],
        not (
            0
            < raw["behavior_weights"]["pv"]
            <= raw["behavior_weights"]["fav"]
            <= raw["behavior_weights"]["cart"]
            <= raw["behavior_weights"]["buy"]
        ),
    ]
    if any(invalid):
        raise ValueError("Invalid feature windows, weights or resource bounds")
    return FeatureSettings(**paths, options=raw)


def feature_connection(
    settings: FeatureSettings, database: Path | None = None
) -> duckdb.DuckDBPyConnection:
    """Open a bounded embedded analytical connection using project-local spill files.

    Args:
        settings: Validated project configuration.
        database: Optional project-confined persistent analytical cache.

    Returns:
        Connection owned and closed by the caller.

    Raises:
        ValueError: A spill or database path escapes the project.
    """
    temporary = project_output_path(settings.output_dir / "spill")
    temporary.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(
        str(project_output_path(database)) if database is not None else ":memory:"
    )
    connection.execute(
        "SET memory_limit = ?", [str(settings.options["memory_mb"]) + "MB"]
    )
    connection.execute("SET threads = ?", [settings.options["threads"]])
    connection.execute("SET temp_directory = ?", [str(temporary)])
    connection.execute("SET preserve_insertion_order = false")
    connection.execute("SET enable_progress_bar = false")
    return connection


def export_relation(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    path: Path,
    parameters: dict[str, Any] | None = None,
    row_group_rows: int = 100000,
) -> dict[str, Any]:
    """Stream a fixed parameterized query to a new compressed Parquet file.

    Args:
        connection: Analytical connection with source views registered.
        query: Fixed or registered-expression SQL.
        path: New project-confined Parquet destination.
        parameters: Named bound values.
        row_group_rows: Maximum rows buffered in one output row group.

    Returns:
        Physical path, row count and stored schema.

    Raises:
        FileExistsError: The destination already exists.
    """
    output = project_output_path(path)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    relation = connection.sql(query, params=parameters)
    relation.write_parquet(
        str(output), compression="zstd", row_group_size=row_group_rows
    )
    stored = connection.read_parquet(str(output))
    return {
        "path": str(output),
        "rows": require_result_row(stored.count("*").fetchone())[0],
        "schema": dict(zip(stored.columns, map(str, stored.types))),
    }


def require_result_row(value: tuple[Any, ...] | None) -> tuple[Any, ...]:
    """Require the one-row result of a declared aggregate or metadata query.

    Args:
        value: Optional row returned by the database interface.

    Returns:
        The available result tuple.

    Raises:
        ValueError: A query expected to return a row returned none.
    """
    if value is None:
        raise ValueError("Expected a database result row")
    return value
