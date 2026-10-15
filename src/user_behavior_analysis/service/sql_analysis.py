"""Execute every registered SQL analysis and export complete bounded results."""

import json
import subprocess
import time
from pathlib import Path
from typing import cast

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]  # No Arrow stubs.
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # No Arrow stubs.

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.sqlite_client import QUERY_NAMES
from user_behavior_analysis.dao.sqlite_client import SQLiteClient
from user_behavior_analysis.dao.sqlite_client import query_path
from user_behavior_analysis.models.database_models import DatabaseAnalysisReport
from user_behavior_analysis.models.database_models import DatabaseAnalysisRequest
from user_behavior_analysis.models.database_models import DatabaseReport
from user_behavior_analysis.models.database_models import QueryEvidence
from user_behavior_analysis.models.database_models import SqlValue
from user_behavior_analysis.service.sql_query_audit import analysis_checks
from user_behavior_analysis.service.sql_query_audit import benchmark_indexes

STRING_COLUMNS = {
    "user_id",
    "item_id",
    "category_id",
    "event_time",
    "next_event_time",
    "first_event_time",
    "last_event_time",
    "event_date",
    "week_start_monday",
    "last_active",
    "last_buy",
    "segment",
}
FLOAT_COLUMNS = {"event_share", "repeat_user_rate_7d"}


def _export_query(
    name: str,
    client: SQLiteClient,
    parameters: dict[str, SqlValue],
    directory: Path,
    chunk_rows: int,
) -> tuple[QueryEvidence, list[dict[str, object]]]:
    start = time.perf_counter()
    rows = 0
    files: list[dict[str, str | int]] = []
    columns: list[str] = []
    preview: list[dict[str, object]] = []
    output = directory / name
    output.mkdir()
    for index, frame in enumerate(
        client.iter_frames(
            query_path(name).read_text(encoding="utf-8"), parameters, chunk_rows
        )
    ):
        columns = frame.columns.tolist()
        if len(preview) < 20:
            preview.extend(
                cast(
                    list[dict[str, object]],
                    json.loads(frame.head(20 - len(preview)).to_json(orient="records")),
                )
            )
        schema = pa.schema(
            [
                pa.field(
                    column,
                    (
                        pa.string()
                        if column in STRING_COLUMNS
                        else pa.float64() if column in FLOAT_COLUMNS else pa.int64()
                    ),
                )
                for column in columns
            ]
        )
        table = pa.Table.from_pandas(
            frame, schema=schema, preserve_index=False, safe=True
        )
        path = output / f"part_{index:05d}.parquet"
        pq.write_table(table, path, compression="zstd", row_group_size=chunk_rows)
        rows += len(frame)
        files.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "name": name,
        "rows": rows,
        "columns": columns,
        "elapsed_seconds": round(time.perf_counter() - start, 4),
        "files": files,
    }, preview


def analyze_database(request: DatabaseAnalysisRequest) -> DatabaseAnalysisReport:
    """Execute complete basic and complex queries on a verified database.

    Args:
        request: Build report, new result directory and analysis window settings.

    Returns:
        All exported relations, logical checks, plans and index observations.

    Raises:
        ValueError: Database fingerprint or window settings are invalid.
        FileExistsError: The result directory exists.
        RuntimeError: Any whole-query consistency gate fails.

    Notes:
        Sequence exports include all observed events; previews are explicitly
        capped at twenty rows and never substitute for complete query exports.
    """
    if not 1 <= request.window_days <= 30 or not 1 <= request.chunk_rows <= 200000:
        raise ValueError("Analysis window or chunk size is outside its allowed range")
    build = cast(
        DatabaseReport,
        json.loads(
            input_file_path(request.database_report).read_text(encoding="utf-8")
        ),
    )
    database = project_output_path(build["database_path"])
    if build["status"] != "passed" or sha256_file(database) != build["database_sha256"]:
        raise ValueError("Database differs from its complete build verification")
    directory = project_output_path(request.output_dir)
    directory.mkdir(parents=True, exist_ok=False)
    client = SQLiteClient(database)
    bounds = client.query_frame(
        "SELECT MIN(event_time) AS first_time, "
        + "MAX(event_time) AS last_time FROM behaviors"
    ).iloc[0]
    start_time = str(bounds["first_time"])
    end_time = (pd.Timestamp(bounds["last_time"]) + pd.Timedelta(hours=1)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    parameters: dict[str, SqlValue] = {
        "start_time": start_time,
        "end_time": end_time,
        "window_days": request.window_days,
        "limit": 50,
    }
    exports: list[QueryEvidence] = []
    summaries: dict[str, list[dict[str, object]]] = {}
    for name in QUERY_NAMES:
        evidence, preview = _export_query(
            name, client, parameters, directory, request.chunk_rows
        )
        exports.append(evidence)
        summaries[name] = preview
    checks = analysis_checks(client, parameters, exports, build["loaded_rows"])
    plans, trials = benchmark_indexes(client, parameters)
    checks["lookup_plans_use_search"] = all(
        any("SEARCH" in step for step in steps) for steps in plans.values()
    )
    checks["database_unchanged"] = sha256_file(database) == build["database_sha256"]
    report: DatabaseAnalysisReport = {
        "status": "passed" if all(checks.values()) else "failed",
        "checked_at_utc": utc_timestamp(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "database_path": build["database_path"],
        "database_sha256": build["database_sha256"],
        "start_time": start_time,
        "end_time_exclusive": end_time,
        "window_days": request.window_days,
        "query_sha256": {name: sha256_file(query_path(name)) for name in QUERY_NAMES},
        "queries": exports,
        "summaries": summaries,
        "query_plans": plans,
        "index_trials": trials,
        "checks": checks,
    }
    write_json(request.report_dir / "analysis.json", report)
    if report["status"] != "passed":
        raise RuntimeError(f"SQL analysis verification failed: {checks}")
    return report
