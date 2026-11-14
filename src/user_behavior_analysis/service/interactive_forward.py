"""Keep user and user-item future associations separate and fully observed."""

from typing import Any

import duckdb
import pandas as pd

from user_behavior_analysis.dao.dashboard_repository import aggregate_records
from user_behavior_analysis.dao.feature_repository import require_result_row


def forward_statistics(
    connection: duckdb.DuckDBPyConnection, end: pd.Timestamp
) -> dict[str, Any]:
    """Use exact-pair future outcomes only when the complete next week is observed.

    Args:
        connection: Filtered historical pair summaries and complete source.
        end: Feature cutoff after the selected end date.

    Returns:
        Mature candidate balance and behavior-depth associations or unavailability.
    """
    source_end = require_result_row(
        connection.execute(
            ("SELECT MAX(event_time)+INTERVAL 1 HOUR FROM s" + "ource")
        ).fetchone()
    )[0]
    mature = end + pd.Timedelta(days=7) <= pd.Timestamp(source_end)
    if not mature:
        return {
            "available": False,
            "reason": "未来7天观测不完整",
            "anchor": str(end),
            "bins": [],
        }
    connection.execute(
        "CREATE TEMP TABLE forward_pairs AS SELECT p.*,COALESCE(f.buy,0) AS target "
        + (
            "FROM pairs p JOIN (SELECT DISTINCT user_id,it"
            + "em_id FROM filtered WHERE event_time>=?) c US"
            + "ING(user_id,item_id) "
        )
        + (
            "LEFT JOIN (SELECT user_id,item_id,1 AS buy FR"
            + "OM source WHERE behavior_type=4 AND event_tim"
            + "e>=? "
        )
        + "AND event_time<? GROUP BY user_id,item_id) f USING(user_id,item_id)",
        [
            (end - pd.Timedelta(days=7)).to_pydatetime(),
            end.to_pydatetime(),
            (end + pd.Timedelta(days=7)).to_pydatetime(),
        ],
    )
    bins: list[dict[str, Any]] = []
    for behavior in ("pv", "cart", "fav"):
        field = behavior + "_records"
        rows = aggregate_records(
            connection,
            "SELECT CASE WHEN "
            + field
            + "=0 THEN '0' WHEN "
            + field
            + "=1 THEN '1' WHEN "
            + field
            + "<5 THEN '2-4' WHEN "
            + field
            + "<10 THEN '5-9' WHEN "
            + field
            + (
                "<20 THEN '10-19' ELSE '20+' END AS bin,COUNT("
                + "*) AS rows,SUM(target)::BIGINT AS positives,"
            )
            + "AVG(target) AS purchase_rate FROM forward_pairs GROUP BY bin",
        )
        bins.extend(dict(row, behavior=behavior) for row in rows)
    balance = aggregate_records(
        connection,
        (
            "SELECT COUNT(*) AS rows,COALESCE(SUM(target),"
            + "0)::BIGINT AS positives FROM forward_pairs"
        ),
    )[0]
    connection.execute(
        (
            "CREATE TEMP TABLE forward_users AS SELECT h.*"
            + ",COALESCE(f.buy,0) AS target FROM (SELECT use"
            + "r_id,SUM(pv_records) AS pv_records,SUM(cart_r"
            + "ecords) AS cart_records,SUM(fav_records) AS f"
            + "av_records FROM pairs GROUP BY user_id) h LEF"
            + "T JOIN (SELECT user_id,1 AS buy FROM source W"
            + "HERE behavior_type=4 AND event_time>=? AND ev"
            + "ent_time<? GROUP BY user_id) f USING(user_id)"
        ),
        [end.to_pydatetime(), (end + pd.Timedelta(days=7)).to_pydatetime()],
    )
    user_bins: list[dict[str, Any]] = []
    for behavior in ("pv", "cart", "fav"):
        field = behavior + "_records"
        rows = aggregate_records(
            connection,
            "SELECT CASE WHEN "
            + field
            + "=0 THEN '0' WHEN "
            + field
            + "=1 THEN '1' WHEN "
            + field
            + "<5 THEN '2-4' WHEN "
            + field
            + "<10 THEN '5-9' WHEN "
            + field
            + (
                "<20 THEN '10-19' ELSE '20+' END AS bin,COUNT("
                + "*) AS rows,SUM(target)::BIGINT AS positives,A"
                + "VG(target) AS purchase_rate FROM forward_user"
                + "s GROUP BY bin"
            ),
        )
        user_bins.extend(dict(row, behavior=behavior) for row in rows)
    user_balance = aggregate_records(
        connection,
        (
            "SELECT COUNT(*) AS rows,COALESCE(SUM(target),"
            + "0)::BIGINT AS positives FROM forward_users"
        ),
    )[0]
    return dict(
        balance,
        available=True,
        anchor=str(end),
        bins=bins,
        user_bins=user_bins,
        user_balance=user_balance,
    )
