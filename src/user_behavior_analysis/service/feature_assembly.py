"""Assemble documented components and export training-compatible entity relations."""

from typing import Any

import duckdb

from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.feature_registry import ENTITY_KEYS
from user_behavior_analysis.service.feature_registry import feature_definition

COMPONENTS = (
    "user_lifecycle",
    "user_preference",
    "user_category_preference",
    "pair_preference",
    "item_business",
    "category_business",
    "user_funnel",
    "item_funnel",
    "category_funnel",
    "user_category_funnel",
    "pair_funnel",
    "user_sequence",
    "user_sequence_runs",
    "user_svd",
    "item_svd",
    "pair_latent",
    "pair_cooccurrence",
)


def time_feature_table(
    connection: duckdb.DuckDBPyConnection, anchor: Any
) -> list[FeatureDefinition]:
    """Record known-at-cutoff calendar candidates without a constant midnight hour.

    Args:
        connection: Snapshot analytical connection.
        anchor: Bound exclusive historical cutoff datetime.

    Returns:
        Calendar definitions; snapshot-constant status is reported by profiling.
    """
    fields = [
        ("time_day_of_week", "isodow($anchor)-1", "截点星期编号，周一为0", "int64"),
        (
            "time_weekday_sin",
            "sin(2*pi()*(isodow($anchor)-1)/7)",
            "截点星期周期正弦",
            "float64",
        ),
        (
            "time_weekday_cos",
            "cos(2*pi()*(isodow($anchor)-1)/7)",
            "截点星期周期余弦",
            "float64",
        ),
        (
            "time_is_weekend",
            "(isodow($anchor)>5)::INTEGER",
            "截点是否周六周日，非法定工作日历",
            "int64",
        ),
        ("time_day_of_month", "day($anchor)", "截点月内日期", "int64"),
    ]
    definitions = [
        feature_definition(
            "time",
            name,
            expression,
            meaning,
            {"family": "日历", "dtype": dtype},
        )
        for name, expression, meaning, dtype in fields
    ]
    connection.execute(
        "CREATE TABLE time_features AS SELECT $anchor::TIMESTAMP AS as_of_time,"
        + ",".join(row["calculation"] + " AS " + row["name"] for row in definitions),
        {"anchor": anchor},
    )
    return definitions


def assemble_entity_views(
    connection: duckdb.DuckDBPyConnection, definitions: list[FeatureDefinition]
) -> None:
    """Join each documented field from exactly one producer without changing grain.

    Args:
        connection: Snapshot containing base statistics and completed components.
        definitions: Actual scalar and sequence definitions.

    Raises:
        ValueError: A field is missing, ambiguous or changes the entity key count.
    """
    columns = {
        name: set(connection.sql("SELECT * FROM " + name + " LIMIT 0").columns)
        for name in COMPONENTS
    }
    for entity, keys in ENTITY_KEYS.items():
        base = entity + "_stats"
        original = set(connection.sql("SELECT * FROM " + base + " LIMIT 0").columns)
        wanted = [
            row
            for row in definitions
            if row["table"] == entity and row["name"] not in original
        ]
        select = ["b.*", "(b.history_coverage_30d=30) AS history_complete_30d"]
        joins = []
        used = set()
        for row in wanted:
            owners = [name for name in COMPONENTS if row["name"] in columns[name]]
            if len(owners) != 1:
                raise ValueError(
                    "Feature producer missing or ambiguous: " + row["name"]
                )
            owner = owners[0]
            alias = "c" + str(COMPONENTS.index(owner))
            if owner not in used:
                join_keys = [key for key in keys if key in columns[owner]]
                if not join_keys:
                    raise ValueError("Component has no entity key: " + owner)
                joins.append(
                    " LEFT JOIN "
                    + owner
                    + " "
                    + alias
                    + " ON "
                    + " AND ".join(
                        "b." + key + "=" + alias + "." + key for key in join_keys
                    )
                )
                used.add(owner)
            expression = alias + "." + row["name"]
            if row["dtype"] == "int64" or row["family"] == "SVD隐式特征":
                expression = "COALESCE(" + expression + ",0)"
            select.append(expression + " AS " + row["name"])
        connection.execute(
            "CREATE OR REPLACE VIEW "
            + entity
            + "_features AS SELECT "
            + ",".join(select)
            + " FROM "
            + base
            + " b"
            + "".join(joins)
        )
        sizes = require_result_row(
            connection.execute(
                "SELECT(SELECT COUNT(*) FROM "
                + base
                + "),"
                + "(SELECT COUNT(*) FROM "
                + entity
                + "_features)"
            ).fetchone()
        )
        if sizes[0] != sizes[1]:
            raise ValueError("Component join changed entity grain: " + entity)


def export_model_inputs(
    connection: duckdb.DuckDBPyConnection,
    settings: FeatureSettings,
    anchor: str,
    definitions: list[FeatureDefinition],
) -> dict[str, Any]:
    """Join one row per historical candidate with every registered scalar feature.

    Args:
        connection: Complete snapshot with entity feature views.
        settings: Output directory.
        anchor: Snapshot calendar date.
        definitions: Produced feature-field definitions.

    Returns:
        Wide-input Parquet schema and exact candidate count.

    Notes:
        This exports historical candidate features, not a sampled/labeled
        train-validation-test dataset.
    """
    aliases = {
        "pair": "p",
        "user": "u",
        "item": "i",
        "category": "c",
        "user_category": "uc",
        "time": "t",
    }
    scalar = [row for row in definitions if row["table"] != "sequence"]
    expressions = [
        "p.as_of_time",
        "p.user_id",
        "p.item_id",
        "p.category_id",
        "p.source_max_event_time AS pair_source_max_event_time",
        "p.history_coverage_30d",
        "p.history_complete_30d",
    ] + [aliases[row["table"]] + "." + row["name"] for row in scalar]
    query = (
        "SELECT "
        + ",".join(expressions)
        + " FROM input_pair p"
        + " JOIN input_user u USING(user_id)"
        + " JOIN input_item i ON p.item_id=i.item_id AND p.category_id=i.category_id"
        + " JOIN input_category c ON p.category_id=c.category_id"
        + " JOIN input_user_category uc ON p.user_id=uc.user_id"
        + " AND p.category_id=uc.category_id CROSS JOIN time_features t"
    )
    directory = settings.output_dir / "snapshots" / anchor
    for entity in ENTITY_KEYS:
        connection.read_parquet(
            str(directory / (entity + "_features.parquet"))
        ).create_view("input_" + entity)
    parts = []
    for bucket in range(16):
        evidence = export_relation(
            connection,
            query + " WHERE hash(p.user_id)%16=$bucket",
            directory / "model_inputs" / ("part_" + str(bucket).zfill(2) + ".parquet"),
            {"bucket": bucket},
            row_group_rows=8192,
        )
        parts.append(evidence)
    expected = require_result_row(
        connection.execute("SELECT COUNT(*) FROM pair_stats").fetchone()
    )[0]
    observed = sum(part["rows"] for part in parts)
    if observed != expected:
        raise ValueError("Wide-input join changed historical candidate coverage")
    return {
        "path": str(directory / "model_inputs"),
        "rows": observed,
        "schema": parts[0]["schema"],
        "parts": parts,
        "scalar_features": len(scalar),
        "keys": ["as_of_time", "user_id", "item_id"],
    }
