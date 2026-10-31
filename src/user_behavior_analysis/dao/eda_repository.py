"""Build reproducible exploratory summaries from the preserved-record database."""

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.local_cache import configure_sqlite_cache
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.eda_models import EDASettings


def load_eda_settings(path: Path) -> EDASettings:
    """Load and validate the configured EDA locations and temporal parameters.

    Args:
        path: Project-relative or absolute configuration file.

    Returns:
        Configuration with project-confined absolute paths.

    Raises:
        ValueError: A path or observation-window setting is invalid.
    """
    source = input_file_path(project_output_path(path))
    raw = json.loads(source.read_text(encoding="utf-8"))
    settings: EDASettings = {
        "database": input_file_path(project_output_path(Path(raw["database"]))),
        "cache_dir": project_output_path(Path(raw["cache_dir"])),
        "report_dir": project_output_path(Path(raw["report_dir"])),
        "anchors": raw["anchors"],
        "history_days": int(raw["history_days"]),
        "label_days": int(raw["label_days"]),
        "transition_max_gap_hours": int(raw["transition_max_gap_hours"]),
        "min_item_view_pairs": int(raw["min_item_view_pairs"]),
        "min_category_view_pairs": int(raw["min_category_view_pairs"]),
        "quadrant_min_view_pairs": int(raw["quadrant_min_view_pairs"]),
    }
    lengths = (
        settings["history_days"],
        settings["label_days"],
        settings["transition_max_gap_hours"],
        settings["min_item_view_pairs"],
        settings["min_category_view_pairs"],
        settings["quadrant_min_view_pairs"],
    )
    if not settings["anchors"] or any(value <= 0 for value in lengths):
        raise ValueError(
            "EDA anchors and positive window/support settings are required"
        )
    return settings


def read_source_frame(
    settings: EDASettings, sql: str, parameters: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Read one bounded EDA result through a read-only SQLite connection.

    Args:
        settings: Validated EDA configuration.
        sql: Fixed project SQL; dynamic values must use named parameters.
        parameters: Values bound to named placeholders.

    Returns:
        The complete query result. Callers select only small EDA tables.
    """
    configure_sqlite_cache()
    with closing(
        sqlite3.connect(settings["database"].as_uri() + "?mode=ro", uri=True)
    ) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA cache_size = -65536")
        return pd.read_sql_query(sql, connection, params=parameters)


def build_eda_cache(settings: EDASettings) -> dict[str, Any]:
    """Materialize local EDA tables without modifying the attached source.

    Args:
        settings: Validated project configuration.

    Returns:
        Source fingerprint, SQL fingerprint and cache build metadata.

    Raises:
        ValueError: An existing cache belongs to a different source or SQL version.
        sqlite3.DatabaseError: A summary cannot be built.
    """
    configure_sqlite_cache()
    cache_dir = settings["cache_dir"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    sql_path = PROJECT_ROOT / "sql/eda/build_cache.sql"
    sql = sql_path.read_text(encoding="utf-8")
    database = settings["database"]
    with database.open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    sql_sha = hashlib.sha256(sql.encode()).hexdigest()
    cache = cache_dir / "eda.sqlite"
    metadata_path = cache_dir / "cache_metadata.json"
    if cache.exists():
        metadata: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata["source_sha256"] != source_sha or metadata["sql_sha256"] != sql_sha:
            raise ValueError("Use a new cache directory after source or SQL changes")
        return metadata
    building = cache_dir / "eda.building.sqlite"
    if building.exists():
        raise ValueError("An unfinished EDA cache exists; inspect it before retrying")
    started = time.perf_counter()
    with closing(sqlite3.connect(building, uri=True)) as connection:
        connection.execute("PRAGMA cache_size = -65536")
        connection.execute("PRAGMA temp_store = FILE")
        connection.execute(
            "ATTACH DATABASE :source AS raw",
            {"source": database.as_uri() + "?mode=ro"},
        )
        # Each statement is fixed SQL from the registered source file.
        for statement in sql.split(";"):
            if statement.strip():
                print(statement.strip().splitlines()[-1][:90], flush=True)
                connection.execute(statement)
                connection.commit()
        totals = connection.execute(
            "SELECT SUM(events), SUM(pv_keys + fav_keys + cart_keys + buy_keys)"
            + " FROM pair_metrics"
        ).fetchone()
        controls = dict(zip(("raw_records", "four_tuple_keys"), totals))
        source_count = connection.execute(
            "SELECT SUM(raw_record_count) FROM raw.user_hour_stats"
        ).fetchone()[0]
        if controls["raw_records"] != source_count:
            raise ValueError("EDA cache does not preserve the source record total")
    building.replace(cache)
    metadata = {
        "source_sha256": source_sha,
        "sql_sha256": sql_sha,
        "database_path": str(database.relative_to(PROJECT_ROOT)),
        "cache_path": str(cache.relative_to(PROJECT_ROOT)),
        "controls": controls,
        "build_seconds": round(time.perf_counter() - started, 3),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def read_cache_frame(
    settings: EDASettings, sql: str, parameters: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Read a selected exploratory aggregate from the local cache.

    Args:
        settings: Validated configuration containing the cache directory.
        sql: Fixed SELECT statement.
        parameters: Named bound SQL values.

    Returns:
        Complete selected aggregate table.
    """
    path = settings["cache_dir"] / "eda.sqlite"
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only = ON")
        return pd.read_sql_query(sql, connection, params=parameters)
