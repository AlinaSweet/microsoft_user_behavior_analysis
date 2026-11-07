"""Describe missing values and effective coverage at candidate-row grain."""

from typing import Any

import duckdb

from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.service.wide_contracts import identifier
from user_behavior_analysis.service.wide_contracts import require_contract


def profile_wide(
    connection: duckdb.DuckDBPyConnection, definitions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Measure all scalar nulls without treating unknown embeddings as real zeros.

    Args:
        connection: Connection containing the completely matched wide view.
        definitions: Scalar dictionary including source family and missing policy.

    Returns:
        Candidate-weighted profiles with explicit missing and coverage semantics.

    Raises:
        ValueError: A numeric feature contains NaN or infinity.

    Notes:
        Entity-table profiles use different denominators. These diagnostics do
        not establish filtering thresholds or fit any preprocessing transform.
    """
    clauses = ["COUNT(*)"]
    for row in definitions:
        field = identifier(row["name"])
        numeric = row["dtype"] != "category"
        clauses.extend(
            [
                "COUNT(*) FILTER(WHERE " + field + " IS NULL)",
                "COUNT(*) FILTER(WHERE " + field + "=0)" if numeric else "NULL",
                (
                    "COUNT(*) FILTER(WHERE "
                    + field
                    + " IS NOT NULL AND NOT isfinite("
                    + field
                    + "))"
                    if numeric
                    else "0"
                ),
            ]
        )
    observed = require_result_row(
        connection.execute("SELECT " + ",".join(clauses) + " FROM wide").fetchone()
    )
    total = int(observed[0])
    result = []
    for index, row in enumerate(definitions):
        missing, zeros, invalid = observed[1 + 3 * index : 4 + 3 * index]
        require_contract(invalid == 0, "Non-finite wide field: " + row["name"])
        result.append(
            {
                "name": row["name"],
                "table": row["table"],
                "family": row["family"],
                "rows": total,
                "missing": missing,
                "missing_rate": missing / total,
                "zero_rate": zeros / total if zeros is not None else None,
                "invalid_values": invalid,
                "unmatched_source_rows": 0,
                "missing_origin": "matched_source_value; see field-specific policy",
                "missing_policy": row["missing_policy"],
            }
        )
    return result


def latent_coverage(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Read availability markers independently of numeric missing rates.

    Args:
        connection: Connection containing the verified wide feature view.

    Returns:
        Candidate-weighted SVD and graph availability where these fields exist.
    """
    result: dict[str, Any] = {}
    for field in ("pair_svd_available", "pair_cooc_graph_known"):
        if field in connection.table("wide").columns:
            result[field] = require_result_row(
                connection.execute("SELECT AVG(" + field + ") FROM wide").fetchone()
            )[0]
    return result
