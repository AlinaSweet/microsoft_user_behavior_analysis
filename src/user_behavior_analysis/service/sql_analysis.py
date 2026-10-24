"""Export registered SQLite analyses as complete bounded local CSV tables."""

import json
import time
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.sqlite_client import QUERY_NAMES
from user_behavior_analysis.dao.sqlite_client import SQLiteClient
from user_behavior_analysis.dao.sqlite_client import query_path
from user_behavior_analysis.models.database_models import SqlValue


def _export(
    client: SQLiteClient, name: str, parameters: dict[str, SqlValue], directory: Path
) -> dict[str, object]:
    """Stream one complete registered query without limiting its exported rows.

    Args:
        client: Read-only connection facade.
        name: Registered SQL filename.
        parameters: Bound source-time and analysis-window values.
        directory: New local result directory.

    Returns:
        Export path, complete row count, content hashes and twenty-row preview.
    """
    started = time.perf_counter()
    destination = directory / (name + ".csv")
    rows = 0
    preview: list[dict[str, object]] = []
    first = True
    for frame in client.iter_frames(
        query_path(name).read_text(encoding="utf-8"), parameters
    ):
        frame.to_csv(
            destination,
            mode="w" if first else "a",
            header=first,
            index=False,
            encoding="utf-8",
        )
        first = False
        rows += len(frame)
        if len(preview) < 20:
            preview.extend(
                json.loads(frame.head(20 - len(preview)).to_json(orient="records"))
            )
    return {
        "name": name,
        "rows": rows,
        "path": str(destination.relative_to(PROJECT_ROOT)),
        "sha256": sha256_file(destination),
        "query_sha256": sha256_file(query_path(name)),
        "seconds": round(time.perf_counter() - started, 4),
        "preview_limit": 20,
        "preview": preview,
    }


def run_sql_analysis(
    database: Path, output: Path, report_dir: Path
) -> dict[str, object]:
    """Execute all registered basic and complex SQL queries on preserved records.

    Args:
        database: Existing project-local content-verified database.
        output: New local directory for complete query result tables.
        report_dir: Destination for small query evidence and summaries.

    Returns:
        Full export identities and direct aggregate consistency checks.

    Raises:
        FileExistsError: Query result directory already exists.
        ValueError: Required reference counts differ or input is empty.
    """
    directory = project_output_path(output)
    directory.mkdir(parents=True, exist_ok=False)
    client = SQLiteClient(database)
    build = json.loads((project_output_path(report_dir) / "database.json").read_text())
    expected_hours = pd.read_csv(
        PROJECT_ROOT
        / "outputs/reports/duplicate_review_20261024/"
        / "high_frequency_user_hours.csv",
        dtype={"user_id": str},
    )
    expected_keys = int(
        pd.read_csv(
            PROJECT_ROOT
            / "outputs/reports/duplicate_review_20261024/key_occurrences.csv"
        )["四元组组数"].sum()
    )
    before = sha256_file(client.database)
    if before != build["database_sha256"] or build["status"] != "passed":
        raise ValueError("Database differs from its complete build verification")
    bounds = client.query_frame(
        "SELECT MIN(event_time) AS start,MAX(event_time) AS stop FROM behaviors"
    ).iloc[0]
    if pd.isna(bounds["start"]):
        raise ValueError("Analysis requires a nonempty fact table")
    parameters: dict[str, SqlValue] = {
        "start_time": str(bounds["start"]),
        "end_time": str(pd.Timestamp(bounds["stop"]) + pd.Timedelta(hours=1)),
        "window_days": 7,
        "limit": 50,
    }
    exports = [_export(client, name, parameters, directory) for name in QUERY_NAMES]
    totals = client.query_frame(
        "SELECT SUM(raw_record_count) AS raw_records,"
        + "SUM(distinct_item_behavior_count) AS business_keys,"
        + "COUNT(*) AS user_hours FROM user_hour_stats"
    ).iloc[0]
    high = client.query_frame(
        "SELECT COUNT(*) AS user_hours,SUM(raw_record_count) AS records,"
        + "COUNT(DISTINCT user_id) AS users FROM high_frequency_user_hours"
    ).iloc[0]
    sample_user = str(
        client.query_frame("SELECT MIN(user_id) AS user_id FROM users").iloc[0][
            "user_id"
        ]
    )
    plans = client.query_frame(
        "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM behaviors "
        + "WHERE user_id=:user_id AND event_time>=:start_time",
        {**parameters, "user_id": sample_user},
    ).to_dict(orient="records")
    checks = {
        "database_unchanged": before == sha256_file(client.database),
        "raw_records_preserved": int(totals["raw_records"]) == build["source_rows"],
        "business_key_reference": int(totals["business_keys"]) == expected_keys,
        "high_frequency_hours": int(high["user_hours"]) == len(expected_hours),
        "high_frequency_records": int(high["records"])
        == int(expected_hours["raw_record_count"].sum()),
    }
    report: dict[str, object] = {
        "status": "passed",
        "database_path": str(client.database.relative_to(PROJECT_ROOT)),
        "database_sha256": before,
        "parameters": parameters,
        "queries": exports,
        "totals": {key: int(value) for key, value in totals.items()},
        "high_frequency": {key: int(value) for key, value in high.items()},
        "query_plan": plans,
        "checks": checks,
        "scope": "Full exports; previews are capped at 20 rows. "
        + "Proxy cohorts are descriptive purchase/high-frequency groups, not RFM. "
        + "Sequences are observed-hour buckets with no fabricated within-hour order.",
    }
    report["status"] = "passed" if all(checks.values()) else "failed"
    write_json(project_output_path(report_dir) / "sql_analysis.json", report)
    if report["status"] != "passed":
        raise ValueError("SQL aggregate controls failed")
    return report
