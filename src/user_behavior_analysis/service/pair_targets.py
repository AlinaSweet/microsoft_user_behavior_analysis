"""Create dense user-item outcomes and independently audit their source facts."""

from typing import Any

import duckdb
import pandas as pd

from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.service.wide_contracts import require_contract


def create_pair_targets(
    connection: duckdb.DuckDBPyConnection, anchor: str, label_days: int = 7
) -> dict[str, Any]:
    """Label historical candidates using purchases of the exact same user/item.

    Args:
        connection: Views wide, all_keys and independent raw_events.
        anchor: Exclusive feature cutoff and inclusive label start.
        label_days: Complete future duration, normally seven days.

    Returns:
        Maturity, class balance, candidate coverage and independent checks.

    Raises:
        ValueError: Keys, boundaries or independent purchase totals disagree.

    Notes:
        Creates temporary future_pairs and targets; never changes source files.
    """
    cutoff = pd.Timestamp(anchor)
    end = cutoff + pd.Timedelta(days=label_days)
    last = require_result_row(
        connection.execute("SELECT MAX(event_time) FROM all_keys").fetchone()
    )[0]
    mature = end <= pd.Timestamp(last) + pd.Timedelta(hours=1)
    parameters = {"cutoff": cutoff.to_pydatetime(), "end": end.to_pydatetime()}
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE future_pairs AS SELECT user_id,item_id,"
        + "SUM(raw_count)::BIGINT AS buy_records,COUNT(*)::BIGINT AS buy_keys "
        + "FROM all_keys WHERE behavior_type=4 AND event_time >= $cutoff "
        + "AND event_time < $end GROUP BY user_id,item_id",
        parameters,
    )
    target = "(COALESCE(f.buy_records,0)>0)::INTEGER" if mature else "NULL::INTEGER"
    count = "COALESCE(f.buy_records,0)" if mature else "NULL::BIGINT"
    keys = "COALESCE(f.buy_keys,0)" if mature else "NULL::BIGINT"
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE targets AS SELECT w.as_of_time,"
        + "w.user_id,w.item_id,$cutoff::TIMESTAMP AS label_start,"
        + "$end::TIMESTAMP AS label_end_exclusive,"
        + target
        + " AS target,"
        + ("TRUE" if mature else "FALSE")
        + " AS target_available,"
        + count
        + " AS future_buy_records,"
        + keys
        + " AS future_buy_keys "
        + "FROM wide w LEFT JOIN future_pairs f USING(user_id,item_id)",
        parameters,
    )
    result = audit_target_alignment(connection, anchor)
    result.update(
        anchor=anchor,
        target_available=mature,
        label_end_exclusive=str(end),
        source_end_exclusive=str(pd.Timestamp(last) + pd.Timedelta(hours=1)),
    )
    if mature:
        result["independent_raw_event_differences"] = _compare_raw_events(
            connection, parameters
        )
        result["candidate_coverage"] = _candidate_coverage(connection)
    else:
        require_contract(result["unavailable"] == result["rows"], "Immature target")
    return result


def audit_target_alignment(
    connection: duckdb.DuckDBPyConnection, anchor: str
) -> dict[str, Any]:
    """Check exact three-key alignment without concealing duplicate records.

    Args:
        connection: Views wide and targets.
        anchor: Expected snapshot date.

    Returns:
        Row counts, class counts and zero-valued integrity counters.

    Raises:
        ValueError: Keys or targets violate the sample contract.
    """
    row = require_result_row(
        connection.execute(
            "SELECT COUNT(*),COUNT(*)-COUNT(DISTINCT(as_of_time,user_id,item_id)),"
            + "COUNT(*) FILTER(WHERE as_of_time IS NULL OR user_id IS NULL "
            + "OR item_id IS NULL OR as_of_time != ?::TIMESTAMP),"
            + "COUNT(*) FILTER(WHERE target_available AND (target IS NULL "
            + "OR target NOT IN (0,1))),COUNT(*) FILTER(WHERE NOT target_available "
            + "AND (target IS NOT NULL OR future_buy_records IS NOT NULL)),"
            + "COUNT(*) FILTER(WHERE target=1),COUNT(*) FILTER(WHERE target=0),"
            + "COUNT(*) FILTER(WHERE NOT target_available) FROM targets",
            [anchor],
        ).fetchone()
    )
    missing = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM ((SELECT as_of_time,user_id,item_id FROM wide "
            + "EXCEPT SELECT as_of_time,user_id,item_id FROM targets) UNION ALL "
            + "(SELECT as_of_time,user_id,item_id FROM targets EXCEPT "
            + "SELECT as_of_time,user_id,item_id FROM wide))"
        ).fetchone()
    )[0]
    require_contract(not any(row[1:5]) and missing == 0, "Target key/value mismatch")
    expected = require_result_row(
        connection.execute("SELECT COUNT(*) FROM wide").fetchone()
    )[0]
    require_contract(row[0] == expected, "Target join changed candidate count")
    return dict(
        zip(
            [
                "rows",
                "duplicate_keys",
                "invalid_keys",
                "invalid_mature_targets",
                "invalid_unavailable_targets",
                "positives",
                "negatives",
                "unavailable",
            ],
            row,
        ),
        key_set_differences=missing,
    )


def _compare_raw_events(
    connection: duckdb.DuckDBPyConnection, parameters: dict[str, Any]
) -> int:
    """Recompute purchase multiplicity from unaggregated independent events.

    Args:
        connection: Raw source, candidates and generated targets.
        parameters: Inclusive cutoff and exclusive future end.

    Returns:
        Zero differences, including positive/negative and raw/key counts.

    Raises:
        ValueError: Any label or multiplicity differs from the raw source.
    """
    differences = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM targets t LEFT JOIN (SELECT user_id,item_id,"
            + "COUNT(*) AS records,COUNT(DISTINCT(event_time,behavior_type)) AS keys "
            + "FROM raw_events WHERE behavior_type=4 AND event_time >= $cutoff "
            + (
                "AND event_time < $end GROUP BY user_id,item_id) r "
                + "USING(user_id,item_id) "
            )
            + "WHERE t.target IS DISTINCT FROM (COALESCE(r.records,0)>0)::INTEGER "
            + "OR t.future_buy_records IS DISTINCT FROM COALESCE(r.records,0) "
            + "OR t.future_buy_keys IS DISTINCT FROM COALESCE(r.keys,0)",
            parameters,
        ).fetchone()
    )[0]
    require_contract(differences == 0, "Raw-event target recomputation differs")
    return int(differences)


def _candidate_coverage(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Measure future purchased pairs reached by the historical candidate rule.

    Args:
        connection: Complete future_pairs and historical wide candidates.

    Returns:
        Pair and record coverage using all observed future purchases as denominator.
    """
    row = require_result_row(
        connection.execute(
            "SELECT COUNT(*),COUNT(w.user_id),SUM(f.buy_records),"
            + "SUM(CASE WHEN w.user_id IS NOT NULL THEN f.buy_records ELSE 0 END) "
            + "FROM future_pairs f LEFT JOIN wide w USING(user_id,item_id)"
        ).fetchone()
    )
    return {
        "denominator": (
            "all future purchased user-item pairs, including ne" + "w users/items"
        ),
        "future_purchase_pairs": row[0],
        "covered_purchase_pairs": row[1],
        "pair_recall": row[1] / row[0] if row[0] else None,
        "future_purchase_records": row[2],
        "covered_purchase_records": row[3],
    }
