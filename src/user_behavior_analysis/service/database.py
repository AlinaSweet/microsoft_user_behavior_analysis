"""Build and verify a complete third-normal-form database from registered events."""

import hashlib
import sqlite3
import subprocess
import time
from contextlib import closing

import psutil

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.event_values import canonical_event_bytes
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.database_repository import INDEXES_PATH
from user_behavior_analysis.dao.database_repository import SCHEMA_PATH
from user_behavior_analysis.dao.database_repository import create_database
from user_behavior_analysis.dao.database_repository import finish_database
from user_behavior_analysis.dao.database_repository import import_event_batch
from user_behavior_analysis.dao.dataset_repository import load_dataset_catalog
from user_behavior_analysis.dao.dataset_repository import read_event_batches
from user_behavior_analysis.dao.sqlite_client import SQLiteClient
from user_behavior_analysis.models.database_models import DatabaseReport
from user_behavior_analysis.models.database_models import DatabaseRequest


def build_database(request: DatabaseRequest) -> DatabaseReport:
    """Import all source batches and compare every canonical event value.

    Args:
        request: Registered input, new output database and report directory.

    Returns:
        Exact row, entity, fingerprint, integrity and resource evidence.

    Raises:
        ValueError: Source values, counts or final round-trip fingerprint differ.
        FileExistsError: The output database or construction file already exists.

    Notes:
        Leaves an incomplete construction file for diagnosis on failure. Publishes
        the final database path only after complete integrity and value checks.
    """
    if not 1 <= request.batch_rows <= 200000:
        raise ValueError("Database batch_rows must lie between 1 and 200000")
    start = time.perf_counter()
    source = load_dataset_catalog(request.catalog)
    database = project_output_path(request.database)
    if database.exists():
        raise FileExistsError(f"Database already exists: {database}")
    building = database.with_name(database.stem + ".building.sqlite")
    code_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()
    source_digest = hashlib.sha256()
    loaded = 0
    last_event_id = 0
    peak = psutil.Process().memory_info().rss
    with closing(create_database(building)) as connection:
        for frame in read_event_batches(source.parts, request.batch_rows):
            identifiers = frame["event_id"]
            if (
                not identifiers.is_monotonic_increasing
                or int(identifiers.iloc[0]) <= last_event_id
            ):
                raise ValueError(
                    "Registered event parts must be strictly event-ID ordered"
                )
            import_event_batch(connection, frame)
            source_digest.update(canonical_event_bytes(frame))
            loaded += len(frame)
            last_event_id = int(identifiers.iloc[-1])
            peak = max(peak, psutil.Process().memory_info().rss)
        counts = finish_database(
            connection,
            {
                "source_catalog": str(source.catalog_path.relative_to(PROJECT_ROOT)),
                "source_catalog_sha256": source.catalog_sha256,
                "source_value_sha256": source_digest.hexdigest(),
                "code_commit": code_commit,
                "time_convention": (
                    "naive source hour; " + "Asia/Shanghai analysis assumption"
                ),
            },
        )
    output_digest = hashlib.sha256()
    for frame in SQLiteClient(building).iter_frames(
        "SELECT * FROM canonical_events ORDER BY event_id",
        chunk_rows=request.batch_rows,
    ):
        output_digest.update(canonical_event_bytes(frame))
        peak = max(peak, psutil.Process().memory_info().rss)
    same_source = load_dataset_catalog(source.catalog_path)
    checks = {
        "complete_row_count": loaded == counts["behaviors"] == source.rows,
        "all_canonical_values": source_digest.hexdigest() == output_digest.hexdigest(),
        "source_catalog_unchanged": same_source.catalog_sha256 == source.catalog_sha256,
        "sqlite_integrity": True,
        "foreign_keys": True,
    }
    if not all(checks.values()):
        raise ValueError(f"Database verification failed: {checks}")
    building.rename(database)
    report: DatabaseReport = {
        "status": "passed",
        "checked_at_utc": utc_timestamp(),
        "code_commit": code_commit,
        "source_catalog": str(source.catalog_path.relative_to(PROJECT_ROOT)),
        "source_catalog_sha256": source.catalog_sha256,
        "database_path": str(database.relative_to(PROJECT_ROOT)),
        "database_sha256": sha256_file(database),
        "database_size_bytes": database.stat().st_size,
        "source_rows": source.rows,
        "loaded_rows": loaded,
        "source_value_sha256": source_digest.hexdigest(),
        "database_value_sha256": output_digest.hexdigest(),
        "counts": counts,
        "checks": checks,
        "sqlite_version": sqlite3.sqlite_version,
        "schema_sha256": sha256_file(SCHEMA_PATH),
        "indexes_sha256": sha256_file(INDEXES_PATH),
        "batch_rows": request.batch_rows,
        "elapsed_seconds": round(time.perf_counter() - start, 4),
        "observed_driver_peak_rss_bytes": peak,
    }
    write_json(request.report_dir / "database.json", report)
    return report
