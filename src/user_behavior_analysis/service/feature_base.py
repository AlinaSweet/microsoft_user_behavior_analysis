"""Rebuild complete-record Parquet and reusable intermediate relations."""

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.event_values import canonical_event_bytes
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.dataset_repository import read_event_batches
from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.models.preprocessing_models import EncodingPlan
from user_behavior_analysis.service.data_encoding import encode_events


def _reencode_records(settings: FeatureSettings) -> dict[str, Any]:
    """Write every validated record with compact types and verify every read-back value.

    Args:
        settings: Validated source catalog and new base directory.

    Returns:
        Counts, exact input fingerprints and canonical round-trip evidence.

    Raises:
        ValueError: A source fingerprint, lineage ordinal or canonical value differs.
        FileExistsError: The new event directory is already populated.
    """
    catalog = json.loads(settings.source_catalog.read_text())
    target = settings.base_dir / "events"
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(target)
    target.mkdir(parents=True, exist_ok=True)
    parts = [PROJECT_ROOT / entry["path"] for entry in catalog["parts"]]
    for path, entry in zip(parts, catalog["parts"]):
        if sha256_file(path) != entry["sha256"]:
            raise ValueError("Validated-record source part changed: " + str(path))
    with closing(
        sqlite3.connect(settings.source_database.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        categories = tuple(
            row[0]
            for row in connection.execute(
                "SELECT category_id FROM categories ORDER BY category_id"
            )
        )
    plan = EncodingPlan(32, categories, catalog["row_count"])
    before = hashlib.sha256()
    after = hashlib.sha256()
    rows = 0
    evidence = []
    for index, frame in enumerate(
        read_event_batches(parts, settings.options["batch_rows"])
    ):
        expected = pd.Series(range(rows + 1, rows + len(frame) + 1)).to_numpy()
        if not (frame["event_id"].to_numpy() == expected).all():
            raise ValueError("Full raw lineage is not complete and contiguous")
        before.update(canonical_event_bytes(frame))
        path = target / f"part_{index:05d}.parquet"
        pq.write_table(
            encode_events(frame, plan),
            path,
            compression="zstd",
            row_group_size=settings.options["batch_rows"],
        )
        restored = pd.read_parquet(path)
        after.update(canonical_event_bytes(restored))
        rows += len(frame)
        evidence.append(
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "rows": len(restored),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if rows != catalog["row_count"] or before.hexdigest() != after.hexdigest():
        raise ValueError("Complete-record Parquet round trip failed")
    return {
        "rows": rows,
        "parts": evidence,
        "input_value_sha256": before.hexdigest(),
        "output_value_sha256": after.hexdigest(),
        "values_match": True,
        "source_csv_sha256": catalog["source_sha256"],
        "policy": "preserve_all_valid_records_flag90",
        "business_key_is_unique": False,
        "record_key": ["event_id"],
    }


def _count_expressions() -> list[str]:
    """Return fixed complete-record and four-tuple aggregation expressions.

    Returns:
        Deterministic SQL expressions with explicit integer storage.
    """
    expressions = [
        "CAST(SUM(raw_count) AS BIGINT) AS event_count",
        "CAST(COUNT(*) AS BIGINT) AS key_count",
    ]
    for code, name in ((1, "pv"), (2, "fav"), (3, "cart"), (4, "buy")):
        expressions.extend(
            [
                "CAST(COALESCE(SUM(raw_count) FILTER (WHERE behavior_type = "
                + str(code)
                + "),0) AS BIGINT) AS "
                + name
                + "_count",
                "CAST(COUNT(*) FILTER (WHERE behavior_type = "
                + str(code)
                + ") AS BIGINT) AS "
                + name
                + "_key_count",
            ]
        )
    return expressions


def _export_intermediates(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings
) -> list[dict[str, Any]]:
    """Export correctly grained reusable full-period relations.

    Args:
        connection: Bounded analytical connection over the new raw event files.
        settings: New base destination.

    Returns:
        Schema, keys, physical row counts and conservation controls per table.
    """
    root = settings.base_dir
    key_query = (
        "SELECT user_id,item_id,category_id,event_time,behavior_type,"
        + " CAST(COUNT(*) AS BIGINT) AS raw_count, MIN(event_id) AS first_event_id"
        + " FROM events GROUP BY user_id,item_id,category_id,event_time,behavior_type"
    )
    key_evidence = export_relation(
        connection, key_query, root / "key_hour" / "data.parquet"
    )
    connection.read_parquet(key_evidence["path"]).create_view("key_hour")
    connection.execute(
        "CREATE VIEW keys AS SELECT *, CAST(event_time AS DATE) AS event_date"
        + " FROM key_hour"
    )
    definitions = [
        (
            "user_daily_stats",
            ["user_id", "event_date"],
            [
                "COUNT(DISTINCT item_id) AS distinct_items",
                "COUNT(DISTINCT category_id) AS distinct_categories",
            ],
        ),
        (
            "item_daily_stats",
            ["item_id", "category_id", "event_date"],
            ["COUNT(DISTINCT user_id) AS distinct_users"],
        ),
        (
            "time_hourly_stats",
            ["event_time", "event_date"],
            [
                "COUNT(DISTINCT user_id) AS distinct_users",
                "COUNT(DISTINCT item_id) AS distinct_items",
                "COUNT(DISTINCT category_id) AS distinct_categories",
            ],
        ),
        (
            "user_item_daily_stats",
            ["user_id", "item_id", "category_id", "event_date"],
            [],
        ),
        (
            "user_category_daily_stats",
            ["user_id", "category_id", "event_date"],
            ["COUNT(DISTINCT item_id) AS distinct_items"],
        ),
    ]
    outputs = [
        dict(
            key_evidence,
            name="key_hour",
            keys=["user_id", "item_id", "behavior_type", "event_time"],
        )
    ]
    for name, keys, additional in definitions:
        expressions = (
            _count_expressions()
            + additional
            + [
                "COUNT(DISTINCT event_time) AS active_hours",
                "MIN(event_time) AS first_event_time",
                "MAX(event_time) AS last_event_time",
            ]
        )
        query = (
            "SELECT "
            + ",".join(keys + expressions)
            + " FROM keys GROUP BY "
            + ",".join(keys)
        )
        evidence = export_relation(
            connection, query, root / "aggregates" / name / "data.parquet"
        )
        controls = require_result_row(
            connection.sql(
                "SELECT SUM(event_count),SUM(key_count) FROM read_parquet($path)",
                params={"path": evidence["path"]},
            ).fetchone()
        )
        outputs.append(
            dict(
                evidence,
                name=name,
                keys=keys,
                event_count=int(controls[0]),
                key_count=int(controls[1]),
            )
        )
        print("intermediate", name, evidence["rows"], flush=True)
    hour_query = (
        "SELECT user_id,event_time,SUM(raw_count)::BIGINT AS raw_record_count,"
        + " COUNT(*) AS distinct_item_behavior_count,"
        + " (SUM(raw_count)-COUNT(*))::BIGINT AS extra_same_key_records,"
        + (
            " MAX(raw_count) AS max_key_occurrences,C"
            + "OUNT(DISTINCT item_id) AS distinct_items"
            + ","
        )
        + " COUNT(DISTINCT behavior_type) AS behavior_type_count,"
        + ",".join(
            "COALESCE(SUM(raw_count) FILTER (WHERE behavior_type="
            + str(code)
            + "),0)::BIGINT AS "
            + name
            + "_count"
            for code, name in ((1, "pv"), (2, "fav"), (3, "cart"), (4, "buy"))
        )
        + " FROM key_hour GROUP BY user_id,event_time"
    )
    hour = export_relation(
        connection, hour_query, root / "aggregates/user_hour_stats/data.parquet"
    )
    outputs.append(dict(hour, name="user_hour_stats", keys=["user_id", "event_time"]))
    return outputs


def _verify_user_hours(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings
) -> dict[str, Any]:
    """Compare all user-hour cells with the previously independently audited source.

    Args:
        connection: Analytical connection for the newly rebuilt base.
        settings: Read-only database and rebuilt user-hour path.

    Returns:
        Number of compared keys and differing values.

    Raises:
        ValueError: A key or any of the ten statistics differs.
    """
    with closing(
        sqlite3.connect(settings.source_database.as_uri() + "?mode=ro", uri=True)
    ) as source:
        reference = pd.read_sql_query("SELECT * FROM user_hour_stats", source)
    reference["event_time"] = pd.to_datetime(reference["event_time"])
    connection.register("reference_hours", reference)
    path = str(settings.base_dir / "aggregates/user_hour_stats/data.parquet")
    columns = [
        column
        for column in reference.columns
        if column not in ("user_id", "event_time")
    ]
    condition = " OR ".join(
        "a." + col + " IS DISTINCT FROM b." + col for col in columns
    )
    query = (
        "SELECT COUNT(*) AS compared,"
        + " COUNT(*) FILTER(WHERE a.user_id IS NULL OR b.user_id IS NULL OR "
        + condition
        + ") AS differences FROM reference_hours a FULL JOIN "
        + "read_parquet($path) b USING(user_id,event_time)"
    )
    counts = require_result_row(connection.sql(query, params={"path": path}).fetchone())
    connection.unregister("reference_hours")
    if counts[1]:
        raise ValueError("Rebuilt user-hour summaries differ from audited source")
    return {
        "compared_user_hours": counts[0],
        "statistics_per_key": len(columns),
        "differences": counts[1],
    }


def build_complete_base(settings: FeatureSettings) -> dict[str, Any]:
    """Rebuild all current intermediates under the confirmed preserve-record policy.

    Args:
        settings: Validated configuration with a new base version directory.

    Returns:
        Complete input, output and full-data conservation evidence.
    """
    catalog_path = PROJECT_ROOT / "data/catalog/base_raw_v2.json"
    if catalog_path.exists():
        catalog: dict[str, Any] = json.loads(catalog_path.read_text())
        for entry in catalog["files"]:
            if sha256_file(PROJECT_ROOT / entry["path"]) != entry["sha256"]:
                raise ValueError("Existing current base file changed")
        return catalog
    started = time.perf_counter()
    records = _reencode_records(settings)
    with feature_connection(settings) as connection:
        connection.read_parquet(
            [str(PROJECT_ROOT / row["path"]) for row in records["parts"]]
        ).create_view("events")
        tables = _export_intermediates(connection, settings)
        expected_keys = require_result_row(
            connection.sql("SELECT COUNT(*) FROM key_hour").fetchone()
        )[0]
        for table in tables:
            if "event_count" in table and (
                table["event_count"] != records["rows"]
                or table["key_count"] != expected_keys
            ):
                raise ValueError("Intermediate conservation failed")
        hour_control = _verify_user_hours(connection, settings)
    files = records["parts"] + [
        {
            "path": str(Path(table["path"]).relative_to(PROJECT_ROOT)),
            "rows": table["rows"],
            "bytes": Path(table["path"]).stat().st_size,
            "sha256": sha256_file(table["path"]),
        }
        for table in tables
    ]
    report = {
        "dataset": "base_raw_v2",
        "status": "completed",
        "source_catalog": str(settings.source_catalog.relative_to(PROJECT_ROOT)),
        "source_catalog_sha256": sha256_file(settings.source_catalog),
        "records": records,
        "tables": tables,
        "files": files,
        "four_tuple_keys": expected_keys,
        "user_hour_control": hour_control,
        "legacy_policy": "clean_v1/events and base_v1 remain historical references",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    write_json(catalog_path, report)
    write_json(settings.report_dir / "base_rebuild.json", report)
    return report
