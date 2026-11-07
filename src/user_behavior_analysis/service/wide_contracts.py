"""Validate snapshot keys, schemas and exact feature joins before registration."""

import re
from typing import Any

import duckdb

from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.service.feature_registry import ENTITY_KEYS

WIDE_KEYS = ["as_of_time", "user_id", "item_id"]
MANAGEMENT = WIDE_KEYS + [
    "category_id",
    "pair_source_max_event_time",
    "history_coverage_30d",
    "history_complete_30d",
]
SOURCE_KEYS = {entity: ["as_of_time"] + keys for entity, keys in ENTITY_KEYS.items()}
SOURCE_KEYS["time"] = ["as_of_time"]


def require_contract(condition: bool, message: str) -> None:
    """Reject a failed persisted-data contract.

    Args:
        condition: Observed success condition.
        message: Context retained in the failed audit.

    Raises:
        ValueError: The condition is false.
    """
    if not condition:
        raise ValueError(message)


def identifier(name: str) -> str:
    """Allow only registered snake_case SQL identifiers.

    Args:
        name: A table or column name from the contract.

    Returns:
        The validated identifier.

    Raises:
        ValueError: The name contains SQL syntax or unexpected characters.
    """
    require_contract(bool(re.fullmatch(r"[a-z][a-z0-9_]*", name)), "Unsafe name")
    return name


def relation_contract(
    connection: duckdb.DuckDBPyConnection, table: str, keys: list[str], anchor: str
) -> dict[str, Any]:
    """Check full relation grain, null keys and exclusive historical boundaries.

    Args:
        connection: Bounded audit connection with the relation registered.
        table: Fixed internal view name.
        keys: Declared unique key, including the cutoff.
        anchor: Expected ISO cutoff date.

    Returns:
        Exact row, duplicate, null and temporal counts.

    Raises:
        ValueError: Grain, cutoff or historical boundaries are invalid.
    """
    table = identifier(table)
    keys = [identifier(key) for key in keys]
    fields = connection.table(table).columns
    nulls = " OR ".join(key + " IS NULL" for key in keys)
    historical = next(
        (field for field in fields if field.endswith("source_max_event_time")), None
    )
    future = (
        "COUNT(*) FILTER(WHERE " + historical + ">=$anchor::TIMESTAMP)"
        if historical
        else "0"
    )
    row = require_result_row(
        connection.execute(
            "SELECT COUNT(*),COUNT(*) FILTER(WHERE "
            + nulls
            + "),COUNT(*) FILTER(WHERE as_of_time<>$anchor::TIMESTAMP),"
            + future
            + " FROM "
            + table,
            {"anchor": anchor},
        ).fetchone()
    )
    duplicate = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM(SELECT "
            + ",".join(keys)
            + " FROM "
            + table
            + " GROUP BY ALL HAVING COUNT(*)>1)"
        ).fetchone()
    )[0]
    result = dict(zip(["rows", "null_keys", "wrong_cutoff", "future_rows"], row))
    result["duplicate_keys"] = duplicate
    require_contract(row[0] > 0, "Empty relation: " + table)
    require_contract(not any(row[1:]) and not duplicate, "Invalid keys/time: " + table)
    return result


def compare_source(
    connection: duckdb.DuckDBPyConnection, entity: str, fields: list[str]
) -> dict[str, Any]:
    """Audit a left join and compare every candidate feature to its entity source.

    Args:
        connection: Connection containing wide and source entity views.
        entity: Registered entity name.
        fields: Exact scalar fields owned by the entity.

    Returns:
        Unmatched row count and per-field exact differences.

    Raises:
        ValueError: A key is unmatched, schema differs or a feature changed.
    """
    keys = SOURCE_KEYS[entity]
    conditions = " AND ".join("w." + key + "=s." + key for key in keys)
    clauses = [
        "COUNT(*)",
        "COUNT(*) FILTER(WHERE s.as_of_time IS NULL)",
    ] + [
        "COUNT(*) FILTER(WHERE w."
        + identifier(field)
        + " IS DISTINCT FROM s."
        + field
        + ")"
        for field in fields
    ]
    wide_types = dict(
        zip(connection.table("wide").columns, connection.table("wide").types)
    )
    source = connection.table("source_" + entity)
    source_types = dict(zip(source.columns, source.types))
    require_contract(
        all(wide_types[field] == source_types[field] for field in fields),
        "Feature type mismatch: " + entity,
    )
    row = require_result_row(
        connection.execute(
            "SELECT "
            + ",".join(clauses)
            + " FROM wide w LEFT JOIN source_"
            + entity
            + " s ON "
            + conditions
        ).fetchone()
    )
    differences = dict(zip(fields, row[2:]))
    result = {
        "joined_rows": row[0],
        "unmatched_rows": row[1],
        "differences": differences,
    }
    require_contract(row[1] == 0, "Unmatched source: " + entity)
    require_contract(not any(differences.values()), "Feature value mismatch: " + entity)
    return result


def compare_candidate_keys(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Check both directions of the exact candidate identity and coverage relation.

    Args:
        connection: Connection with wide and source_pair views.

    Returns:
        Missing and unexpected candidate-management rows, both required to be zero.

    Raises:
        ValueError: Any candidate or management value is lost or changed.
    """
    source_fields = [
        (
            "source_max_event_time AS pair_source_max_event_time"
            if field == "pair_source_max_event_time"
            else field
        )
        for field in MANAGEMENT
    ]
    source = "SELECT " + ",".join(source_fields) + " FROM source_pair"
    wide = "SELECT " + ",".join(MANAGEMENT) + " FROM wide"
    result = {}
    for name, left, right in [("missing", source, wide), ("unexpected", wide, source)]:
        result[name] = int(
            require_result_row(
                connection.execute(
                    "SELECT COUNT(*) FROM((" + left + ") EXCEPT (" + right + "))"
                ).fetchone()
            )[0]
        )
    require_contract(not any(result.values()), "Candidate keys or metadata changed")
    return result
