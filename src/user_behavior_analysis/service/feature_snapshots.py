"""Build time-correct user, item, category and interaction feature snapshots."""

from datetime import datetime
from datetime import timedelta
from typing import Any

import duckdb

from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.feature_registry import ENTITY_KEYS
from user_behavior_analysis.service.feature_registry import derived_feature_definitions
from user_behavior_analysis.service.feature_registry import window_feature_definitions


def snapshot_parameters(anchor: str, windows: list[int]) -> dict[str, Any]:
    """Build bound historical boundaries for a midnight cutoff.

    Args:
        anchor: ISO calendar date for the exclusive history boundary.
        windows: Positive historical window lengths.

    Returns:
        Bound datetime values for the cutoff and historical starts.
    """
    cutoff = datetime.fromisoformat(anchor)
    return {
        "anchor": cutoff,
        **{"start_" + str(days): cutoff - timedelta(days=days) for days in windows},
    }


def create_history_view(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings, anchor: str
) -> dict[str, Any]:
    """Materialize only the key records strictly preceding the requested cutoff.

    Args:
        connection: Bounded per-snapshot connection.
        settings: Current complete-record base.
        anchor: Exclusive history cutoff.

    Returns:
        Boundaries, control counts and actual observation coverage.
    """
    connection.read_parquet(
        str(settings.base_dir / "key_hour/data.parquet")
    ).create_view("all_keys")
    parameters = snapshot_parameters(anchor, settings.options["windows"])
    if not require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='history'"
        ).fetchone()
    )[0]:
        connection.execute(
            "CREATE TABLE history AS SELECT *,CAST(event_time AS DATE) AS event_date"
            + " FROM all_keys WHERE event_time < $anchor",
            {"anchor": parameters["anchor"]},
        )
    bounds = require_result_row(
        connection.execute(
            (
                "SELECT MIN(event_time),MAX(event_time),S"
                + "UM(raw_count),COUNT(*) FROM history"
            )
        ).fetchone()
    )
    coverage = (parameters["anchor"] - bounds[0]).total_seconds() / 86400
    return {
        "parameters": parameters,
        "first_event_time": str(bounds[0]),
        "last_event_time": str(bounds[1]),
        "raw_records": bounds[2],
        "key_rows": bounds[3],
        "coverage": {
            days: min(days, int(coverage)) for days in settings.options["windows"]
        },
    }


def build_statistical_tables(
    connection: duckdb.DuckDBPyConnection,
    settings: FeatureSettings,
    anchor: str,
    history: dict[str, Any],
) -> list[FeatureDefinition]:
    """Materialize entity statistics and their exact dictionary definitions.

    Args:
        connection: Per-snapshot cache containing strictly historical keys.
        settings: Windows and snapshot destination.
        anchor: Snapshot date.
        history: Bound parameters and actual coverage.

    Returns:
        Definitions of every materialized base and derived field.
    """
    definitions = []
    for table, keys in ENTITY_KEYS.items():
        base = window_feature_definitions(table, settings.options["windows"])
        derived = derived_feature_definitions(
            table, settings.options["behavior_weights"]
        )
        expressions = [row["calculation"] + " AS " + row["name"] for row in base]
        coverage = [
            str(history["coverage"][days])
            + "::INTEGER AS history_coverage_"
            + str(days)
            + "d"
            for days in settings.options["windows"]
        ]
        management = [
            "$anchor::TIMESTAMP AS as_of_time",
            "MIN(event_time) AS source_min_event_time",
            "MAX(event_time) AS source_max_event_time",
        ] + coverage
        query = (
            "SELECT "
            + ",".join(keys + management + expressions)
            + " FROM history GROUP BY "
            + ",".join(keys)
        )
        if table == "pair":
            query += " HAVING MAX(event_time) >= $start_7"
        already = require_result_row(
            connection.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=$name",
                {"name": table + "_stats"},
            ).fetchone()
        )[0]
        if already:
            definitions.extend(base + derived)
            continue
        if table == "user_category":
            connection.execute("DROP TABLE IF EXISTS user_category_base")
            for bucket in range(8):
                partitioned = query.replace(
                    " FROM history GROUP BY",
                    " FROM history WHERE hash(user_id)%8=$bucket GROUP BY",
                )
                statement = (
                    "CREATE TABLE user_category_base AS "
                    if bucket == 0
                    else "INSERT INTO user_category_base "
                )
                connection.execute(
                    statement + partitioned, dict(history["parameters"], bucket=bucket)
                )
        else:
            connection.execute(
                "CREATE TABLE " + table + "_base AS " + query, history["parameters"]
            )
        query = (
            "SELECT *,"
            + ",".join(row["calculation"] + " AS " + row["name"] for row in derived)
            + " FROM "
            + table
            + "_base"
        )
        connection.execute("CREATE TABLE " + table + "_stats AS " + query)
        connection.execute(
            "CREATE VIEW " + table + "_features AS SELECT * FROM " + table + "_stats"
        )
        definitions.extend(base + derived)
        print(
            "snapshot",
            anchor,
            table,
            require_result_row(
                connection.execute(
                    "SELECT COUNT(*) FROM " + table + "_features"
                ).fetchone()
            )[0],
            flush=True,
        )
    return definitions


def export_snapshot_entities(
    connection: duckdb.DuckDBPyConnection, settings: FeatureSettings, anchor: str
) -> dict[str, Any]:
    """Persist augmented entity tables with explicit primary keys.

    Args:
        connection: Snapshot cache containing completed feature tables.
        settings: Feature output directory.
        anchor: Snapshot calendar date.

    Returns:
        Export schemas, row counts and key definitions.
    """
    result = {}
    directory = settings.output_dir / "snapshots" / anchor
    for table, keys in ENTITY_KEYS.items():
        evidence = export_relation(
            connection,
            "SELECT * FROM " + table + "_features",
            directory / (table + "_features.parquet"),
            row_group_rows=8192,
        )
        result[table] = dict(evidence, keys=["as_of_time"] + keys)
    return result
