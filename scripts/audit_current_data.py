"""Independently reconcile current complete-record data and feature snapshots."""

import json
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.dao.sqlite_client import SQLiteClient
from user_behavior_analysis.models.feature_models import FeatureSettings

REPORT = PROJECT_ROOT / "outputs/reports/delivery_review_20261031"


def _require(condition: bool, message: str) -> None:
    """Stop reconciliation when a declared independent control fails.

    Args:
        condition: Actual comparison result.
        message: Specific discrepancy to report.

    Raises:
        ValueError: The comparison fails.
    """
    if not condition:
        raise ValueError(message)


def _database_controls(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings
) -> dict[str, Any]:
    """Compare all ten user-hour measures and inspect database integrity.

    Args:
        connection: Bounded DuckDB connection owned by the caller.
        settings: Current database and complete-record base locations.

    Returns:
        Actual integrity results and full user-hour comparison dimensions.
    """
    client = SQLiteClient(settings.source_database)
    integrity = client.query_frame("PRAGMA quick_check").iloc[:, 0].tolist()
    foreign_keys = client.query_frame("PRAGMA foreign_key_check")
    rows = 0
    metrics = []
    for frame in client.iter_frames("SELECT * FROM user_hour_stats"):
        frame["event_time"] = pd.to_datetime(frame["event_time"])
        connection.register("hour_batch", frame)
        statement = (
            "CREATE TABLE database_hours AS "
            if rows == 0
            else "INSERT INTO database_hours "
        )
        connection.execute(statement + "SELECT * FROM hour_batch")
        connection.unregister("hour_batch")
        rows += len(frame)
        metrics = [
            name for name in frame.columns if name not in ("user_id", "event_time")
        ]
    connection.read_parquet(
        str(settings.base_dir / "aggregates/user_hour_stats/data.parquet")
    ).create_view("base_hours")
    mismatches = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM database_hours d FULL OUTER JOIN base_hours b "
            + "USING(user_id,event_time) WHERE "
            + " OR ".join(
                "d." + name + " IS DISTINCT FROM b." + name for name in metrics
            )
        ).fetchone()
    )[0]
    _require(integrity == ["ok"], "SQLite quick_check failed")
    _require(foreign_keys.empty, "SQLite foreign-key violations")
    _require(mismatches == 0, "Current user-hour measures differ from SQLite")
    return {
        "quick_check": integrity,
        "foreign_key_violations": len(foreign_keys),
        "user_hours": rows,
        "metrics": metrics,
        "different_rows": mismatches,
    }


def _snapshot_controls(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings, anchor: str
) -> dict[str, Any]:
    """Recompute feature counts and future outcomes from base keys independently.

    Args:
        connection: Bounded connection with all_keys registered.
        settings: Completed feature locations and window settings.
        anchor: Historical cutoff to inspect.

    Returns:
        Full-population discrepancies for counts, candidate keys and future labels.
    """
    directory = settings.output_dir / "snapshots" / anchor
    cutoff = datetime.fromisoformat(anchor)
    parameters = {"cutoff": cutoff, "start": cutoff - timedelta(days=7)}
    connection.read_parquet(str(directory / "model_inputs/*.parquet")).create_view(
        "current_inputs", replace=True
    )
    connection.read_parquet(str(directory / "user_features.parquet")).create_view(
        "current_users", replace=True
    )
    connection.read_parquet(str(directory / "user_targets.parquet")).create_view(
        "current_targets", replace=True
    )
    columns = connection.sql("SELECT * FROM current_inputs LIMIT 0").columns
    dictionary = json.loads(
        (settings.report_dir / "feature_dictionary.json").read_text(encoding="utf-8")
    )
    expected = {r["name"] for r in dictionary["features"] if r["table"] != "sequence"}
    management = {
        "as_of_time",
        "user_id",
        "item_id",
        "category_id",
        "pair_source_max_event_time",
        "history_coverage_30d",
        "history_complete_30d",
    }
    _require(set(columns) == expected | management, "Model-input dictionary differs")
    totals = require_result_row(
        connection.execute(
            "SELECT COUNT(*),COUNT(DISTINCT(user_id,item_id)),"
            + "COUNT(*) FILTER(WHERE pair_source_max_event_time >= $cutoff "
            + "OR as_of_time IS DISTINCT FROM $cutoff) FROM current_inputs",
            {"cutoff": cutoff},
        ).fetchone()
    )
    pair_differences = require_result_row(
        connection.execute(
            "WITH source AS(SELECT user_id,item_id,SUM(raw_count) AS raw,"
            + "COUNT(*) AS keys FROM all_keys WHERE event_time >= $start "
            + "AND event_time < $cutoff GROUP BY user_id,item_id) "
            + "SELECT COUNT(*) FROM current_inputs p FULL OUTER JOIN source s "
            + "USING(user_id,item_id) WHERE p.pair_event_count_7d "
            + "IS DISTINCT FROM s.raw "
            + "OR p.pair_key_count_7d IS DISTINCT FROM s.keys",
            parameters,
        ).fetchone()
    )[0]
    user_differences = require_result_row(
        connection.execute(
            "WITH source AS(SELECT user_id,SUM(raw_count) AS raw,COUNT(*) AS keys "
            + "FROM all_keys WHERE event_time >= $start AND event_time < $cutoff "
            + "GROUP BY user_id) SELECT COUNT(*) FROM current_users u LEFT JOIN "
            + "source s USING(user_id) WHERE u.user_event_count_7d "
            + "IS DISTINCT FROM COALESCE(s.raw,0) OR u.user_key_count_7d "
            + "IS DISTINCT FROM COALESCE(s.keys,0)",
            parameters,
        ).fetchone()
    )[0]
    last = require_result_row(
        connection.execute("SELECT MAX(event_time) FROM all_keys").fetchone()
    )[0]
    label_end = cutoff + timedelta(days=7)
    mature = label_end <= last + timedelta(hours=1)
    if mature:
        label_differences = require_result_row(
            connection.execute(
                "WITH future AS(SELECT DISTINCT user_id FROM all_keys "
                + "WHERE event_time >= $cutoff AND event_time < $end "
                + "AND behavior_type=4) SELECT COUNT(*) FROM current_targets t "
                + "LEFT JOIN future f USING(user_id) WHERE t.target "
                + "IS DISTINCT FROM (f.user_id IS NOT NULL)::INTEGER "
                + "OR t.target_available IS DISTINCT FROM TRUE",
                {"cutoff": cutoff, "end": label_end},
            ).fetchone()
        )[0]
    else:
        label_differences = require_result_row(
            connection.execute(
                "SELECT COUNT(*) FROM current_targets WHERE target IS NOT NULL "
                + "OR target_available IS DISTINCT FROM FALSE"
            ).fetchone()
        )[0]
    _require(totals[0] == totals[1], "Duplicate candidate keys")
    _require(totals[2] == 0, "Future input or wrong cutoff")
    _require(pair_differences == 0, "Pair counts do not match independent source")
    _require(user_differences == 0, "User counts do not match independent source")
    _require(label_differences == 0, "Future targets do not match source")
    return {
        "anchor": anchor,
        "candidate_rows": totals[0],
        "scalar_fields": len(expected),
        "duplicate_candidates": totals[0] - totals[1],
        "future_or_cutoff_violations": totals[2],
        "pair_count_differences": pair_differences,
        "user_count_differences": user_differences,
        "label_available": mature,
        "label_differences": label_differences,
    }


def main() -> int:
    """Run fresh independent controls without changing source data or features.

    Returns:
        Zero after every control agrees; failures stop with the discrepancy.
    """
    settings = load_feature_settings(Path("configs/feature_system.json"))
    with feature_connection(settings) as connection:
        connection.read_parquet(
            str(settings.base_dir / "key_hour/data.parquet")
        ).create_view("all_keys")
        database = _database_controls(connection, settings)
        snapshots = []
        for anchor in settings.options["anchors"]:
            snapshots.append(_snapshot_controls(connection, settings, anchor))
            print("independent snapshot passed: " + anchor, flush=True)
    sql = json.loads(
        (
            PROJECT_ROOT / "outputs/reports/stage2_step1_20261024/sql_analysis.json"
        ).read_text()
    )
    for query in sql["queries"]:
        _require(
            query["query_sha256"]
            == sha256_file(PROJECT_ROOT / "sql/queries" / (query["name"] + ".sql")),
            "Previously audited SQL changed: " + query["name"],
        )
    report = {
        "status": "passed",
        "checked_at_utc": utc_timestamp(),
        "scope": (
            "Fresh SQLite integrity and all user-hour measures; "
            + "full candidate/user 7d counts and future labels"
        ),
        "database": database,
        "snapshots": snapshots,
        "unchanged_audited_sql_queries": len(sql["queries"]),
    }
    write_json(REPORT / "independent_data_audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
