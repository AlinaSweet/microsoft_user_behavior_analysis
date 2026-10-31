"""Profile real feature values and verify temporal and count invariants."""

from typing import Any

import duckdb
import pandas as pd

from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.models.feature_models import FeatureDefinition
from user_behavior_analysis.models.feature_models import FeatureSettings


def profile_features(
    connection: duckdb.DuckDBPyConnection,
    definitions: list[FeatureDefinition],
    anchor: str,
) -> list[dict[str, Any]]:
    """Calculate full-data missing, zero, finite and constant-field diagnostics.

    Args:
        connection: Complete entity feature views.
        definitions: Registered field definitions.
        anchor: Snapshot date.

    Returns:
        Per-feature quality rows; distinct counts are explicitly approximate.

    Raises:
        ValueError: A numeric field contains an infinite or NaN value.
    """
    output = []
    for entity in ("user", "item", "category", "pair", "user_category", "time"):
        fields = [row for row in definitions if row["table"] == entity]
        expressions = ["COUNT(*) AS row_count"]
        for index, row in enumerate(fields):
            field = row["name"]
            prefix = "f" + str(index) + "_"
            expressions.extend(
                [
                    "COUNT(" + field + ") AS " + prefix + "nonnull",
                    "approx_count_distinct(" + field + ") AS " + prefix + "distinct",
                ]
            )
            if row["dtype"] == "category":
                continue
            expressions.extend(
                [
                    "MIN(" + field + ")::DOUBLE AS " + prefix + "min",
                    "MAX(" + field + ")::DOUBLE AS " + prefix + "max",
                    "COUNT(*) FILTER(WHERE " + field + "=0) AS " + prefix + "zeros",
                    "COUNT(*) FILTER(WHERE "
                    + field
                    + " IS NOT NULL"
                    + " AND NOT isfinite("
                    + field
                    + ")) AS "
                    + prefix
                    + "invalid",
                ]
            )
        frame = (
            connection.execute(
                "SELECT " + ",".join(expressions) + " FROM " + entity + "_features"
            )
            .df()
            .iloc[0]
        )
        total = int(frame["row_count"])
        for index, row in enumerate(fields):
            prefix = "f" + str(index) + "_"
            nonnull = int(frame[prefix + "nonnull"])
            minimum = (
                None
                if row["dtype"] == "category" or pd.isna(frame[prefix + "min"])
                else float(frame[prefix + "min"])
            )
            maximum = (
                None
                if row["dtype"] == "category" or pd.isna(frame[prefix + "max"])
                else float(frame[prefix + "max"])
            )
            invalid = (
                0 if row["dtype"] == "category" else int(frame[prefix + "invalid"])
            )
            if invalid:
                raise ValueError("Non-finite feature values: " + row["name"])
            output.append(
                {
                    "anchor": anchor,
                    "table": entity,
                    "name": row["name"],
                    "family": row["family"],
                    "rows": total,
                    "nonnull": nonnull,
                    "missing_rate": 1 - nonnull / total if total else None,
                    "zero_rate": (
                        None
                        if row["dtype"] == "category" or not total
                        else int(frame[prefix + "zeros"]) / total
                    ),
                    "approx_distinct": int(frame[prefix + "distinct"]),
                    "minimum": minimum,
                    "maximum": maximum,
                    "constant_in_snapshot": nonnull > 0
                    and (
                        int(frame[prefix + "distinct"]) <= 1
                        if row["dtype"] == "category"
                        else minimum == maximum
                    ),
                    "all_missing": nonnull == 0,
                    "invalid_values": invalid,
                }
            )
    return output


def temporal_count_controls(
    connection: duckdb.DuckDBPyConnection, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Verify history-only boundaries and raw/key conservation across entity grains.

    Args:
        connection: Complete snapshot cache.
        parameters: Cutoff and historical starts.

    Returns:
        Per-grain counts and temporal-violation totals.

    Raises:
        ValueError: A future event, duplicate key or count mismatch is found.
    """
    future = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM history WHERE event_time >= $anchor",
            {"anchor": parameters["anchor"]},
        ).fetchone()
    )[0]
    source = require_result_row(
        connection.execute(
            "SELECT SUM(raw_count),COUNT(*) FROM history WHERE event_time >= $start_7",
            {"start_7": parameters["start_7"]},
        ).fetchone()
    )
    controls = []
    for entity in ("user", "item", "category", "pair", "user_category"):
        row = require_result_row(
            connection.execute(
                "SELECT COUNT(*),SUM("
                + entity
                + "_event_count_7d),SUM("
                + entity
                + (
                    "_key_count_7d),COUNT(*) FILTER(WHERE sou"
                    + "rce_max_event_time >= $anchor)"
                )
                + " FROM "
                + entity
                + "_features",
                {"anchor": parameters["anchor"]},
            ).fetchone()
        )
        matches = int(row[1]) == int(source[0]) and int(row[2]) == int(source[1])
        controls.append(
            {
                "entity": entity,
                "rows": row[0],
                "raw_count_7d": int(row[1]),
                "key_count_7d": int(row[2]),
                "future_rows": row[3],
                "counts_match": matches,
            }
        )
        if not matches or row[3]:
            raise ValueError("Temporal or conservation control failed: " + entity)
    duplicate_pairs = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM(SELECT user_id,item_id FROM pair_features"
            + " GROUP BY user_id,item_id HAVING COUNT(*)>1)"
        ).fetchone()
    )[0]
    if future or duplicate_pairs:
        raise ValueError("Future events or duplicate candidate keys")
    return {
        "future_events": future,
        "duplicate_candidate_keys": duplicate_pairs,
        "expected_raw_records_7d": int(source[0]),
        "expected_key_rows_7d": int(source[1]),
        "entity_controls": controls,
    }


def export_user_targets(
    connection: duckdb.DuckDBPyConnection,
    settings: FeatureSettings,
    anchor: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Keep observed future user outcomes separate from all historical features.

    Args:
        connection: Snapshot cache with all_keys and historical user population.
        settings: Feature output directory and label length.
        anchor: Snapshot date.
        parameters: Bound cutoff datetime.

    Returns:
        Target-table path, maturity and actual observed class counts.

    Notes:
        These user-level exploratory outcomes do not construct the stage-three
        user-item training dataset or define its class balance.
    """
    cutoff = pd.Timestamp(parameters["anchor"])
    last = require_result_row(
        connection.execute("SELECT MAX(event_time) FROM all_keys").fetchone()
    )[0]
    end = cutoff + pd.Timedelta(days=settings.options["label_days"])
    mature = end <= pd.Timestamp(last) + pd.Timedelta(hours=1)
    if mature:
        query = (
            "SELECT u.user_id,$anchor::TIMESTAMP AS as_of_time,"
            + (
                "(COALESCE(f.buy_records,0)>0)::INTEGER A"
                + "S target,TRUE AS target_available"
            )
            + (
                " FROM user_stats u LEFT JOIN(SELECT user"
                + "_id,SUM(raw_count) AS buy_records"
            )
            + " FROM all_keys WHERE event_time >= $anchor AND event_time < $label_end"
            + " AND behavior_type=4 GROUP BY user_id)f USING(user_id)"
        )
        values = {"anchor": parameters["anchor"], "label_end": end.to_pydatetime()}
    else:
        query = (
            "SELECT user_id,$anchor::TIMESTAMP AS as_of_time,"
            + "NULL::INTEGER AS target,FALSE AS target_available FROM user_stats"
        )
        values = {"anchor": parameters["anchor"]}
    connection.execute("CREATE TABLE user_targets AS " + query, values)
    evidence = export_relation(
        connection,
        "SELECT * FROM user_targets",
        settings.output_dir / "snapshots" / anchor / "user_targets.parquet",
    )
    counts = require_result_row(
        connection.execute(
            "SELECT COUNT(*),SUM(target=1),SUM(target=0) FROM user_targets"
        ).fetchone()
    )
    return dict(
        evidence,
        label_available=mature,
        users=counts[0],
        positives=counts[1],
        negatives=counts[2],
        label_end_exclusive=str(end),
    )
