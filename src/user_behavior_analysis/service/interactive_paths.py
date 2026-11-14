"""Compute mature strict paths and hourly multi-label transitions after filtering."""

from typing import Any

import duckdb
import pandas as pd

from user_behavior_analysis.dao.feature_repository import require_result_row


def path_statistics(
    connection: duckdb.DuckDBPyConnection, end: pd.Timestamp
) -> dict[str, Any]:
    """Require complete seven-day follow-up and strict cross-hour stage order.

    Args:
        connection: Read-only source with the globally filtered relation.
        end: Exclusive end of the selected calendar interval.

    Returns:
        Mature pair funnel and optional-path counts with shared denominators.
    """
    connection.execute(
        "CREATE TEMP TABLE mature_pv AS SELECT user_id,item_id,MIN(event_time) AS pv "
        + "FROM filtered WHERE behavior_type=1 GROUP BY user_id,item_id "
        + "HAVING MIN(event_time)+INTERVAL 7 DAY <= ?",
        [end.to_pydatetime()],
    )
    connection.execute(
        "CREATE TEMP TABLE carts AS SELECT p.*,MIN(f.event_time) AS cart "
        + (
            "FROM mature_pv p LEFT JOIN filtered f ON p.us"
            + "er_id=f.user_id AND p.item_id=f.item_id "
        )
        + (
            "AND f.behavior_type=3 AND f.event_time>p.pv A"
            + "ND f.event_time<p.pv+INTERVAL 7 DAY GROUP BY "
            + "ALL"
        )
    )
    connection.execute(
        "CREATE TEMP TABLE favorites AS SELECT p.*,MIN(f.event_time) AS fav "
        + (
            "FROM carts p LEFT JOIN filtered f ON p.user_i"
            + "d=f.user_id AND p.item_id=f.item_id "
        )
        + (
            "AND f.behavior_type=2 AND f.event_time>p.cart"
            + " AND f.event_time<p.pv+INTERVAL 7 DAY GROUP B"
            + "Y ALL"
        )
    )
    row = require_result_row(
        connection.execute(
            (
                "SELECT COUNT(*),COUNT(cart),COUNT(fav),COUNT("
                + "buy) FROM (SELECT p.*,MIN(f.event_time) AS bu"
                + "y "
            )
            + (
                "FROM favorites p LEFT JOIN filtered f ON p.us"
                + "er_id=f.user_id AND p.item_id=f.item_id "
            )
            + (
                "AND f.behavior_type=4 AND f.event_time>p.fav "
                + "AND f.event_time<p.pv+INTERVAL 7 DAY GROUP BY"
                + " ALL)"
            )
        ).fetchone()
    )
    alternative = require_result_row(
        connection.execute(
            (
                "SELECT COUNT(*) FILTER(WHERE strict_buy IS NO"
                + "T NULL),COUNT(*) FILTER(WHERE tied_buy IS NOT"
                + " NULL) "
            )
            + (
                "FROM (SELECT p.*,MIN(f.event_time) FILTER(WHE"
                + "RE f.event_time>p.pv) AS strict_buy,"
            )
            + (
                "MIN(f.event_time) AS tied_buy FROM mature_pv "
                + "p LEFT JOIN filtered f ON p.user_id=f.user_id"
                + " "
            )
            + "AND p.item_id=f.item_id AND f.behavior_type=4 AND f.event_time>=p.pv "
            + "AND f.event_time<p.pv+INTERVAL 7 DAY GROUP BY ALL)"
        ).fetchone()
    )
    return {
        "stage_counts": list(row or [0, 0, 0, 0]),
        "pv_to_buy_strict": alternative[0] if alternative else 0,
        "pv_to_buy_same_hour_candidates": alternative[1] if alternative else 0,
        "maturity_days": 7,
    }


def transition_statistics(
    connection: duckdb.DuckDBPyConnection,
) -> list[dict[str, Any]]:
    """Count next-observed-hour masks without inventing within-hour order or exits.

    Args:
        connection: Globally filtered source records.

    Returns:
        Sixteen source/next behavior combinations with explicit denominators.
    """
    connection.execute(
        "CREATE TEMP TABLE observed_hours AS SELECT user_id,event_time,"
        + (
            "bit_or(1::INTEGER << (behavior_type-1)::INTEG"
            + "ER) AS mask FROM filtered GROUP BY user_id,ev"
            + "ent_time"
        )
    )
    connection.execute(
        (
            "CREATE TEMP TABLE observed_next AS SELECT *,L"
            + "EAD(event_time) OVER w AS next_time,"
        )
        + (
            "LEAD(mask) OVER w AS next_mask FROM observed_"
            + "hours WINDOW w AS (PARTITION BY user_id ORDER"
            + " BY event_time)"
        )
    )
    result = []
    for current in range(4):
        for following in range(4):
            row = require_result_row(
                connection.execute(
                    (
                        "SELECT COUNT(*),COUNT(*) FILTER(WHERE (next_m"
                        + "ask & ?) > 0) FROM observed_next "
                    )
                    + "WHERE (mask & ?) > 0 AND next_time<=event_time+INTERVAL 24 HOUR",
                    [1 << following, 1 << current],
                ).fetchone()
            )
            count, matched = row or (0, 0)
            result.append(
                {
                    "current": current + 1,
                    "following": following + 1,
                    "denominator": count,
                    "matched": matched,
                    "rate": matched / count if count else None,
                }
            )
    return result
