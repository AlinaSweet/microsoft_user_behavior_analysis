"""Check complete SQL outputs and observe indexed versus scan execution."""

import time
from typing import cast

from user_behavior_analysis.dao.sqlite_client import SQLiteClient
from user_behavior_analysis.dao.sqlite_client import query_path
from user_behavior_analysis.models.database_models import IndexTrial
from user_behavior_analysis.models.database_models import QueryEvidence
from user_behavior_analysis.models.database_models import SqlValue


def analysis_checks(
    client: SQLiteClient,
    parameters: dict[str, SqlValue],
    exports: list[QueryEvidence],
    expected_rows: int,
) -> dict[str, bool]:
    """Cross-check full SQL distributions, windows, sequence and proxy outputs.

    Args:
        client: Read-only verified database client.
        parameters: Bound complete-observation query values.
        exports: Whole exported query row counts.
        expected_rows: Canonical database event count.

    Returns:
        Explicit logical gates; unit fixtures separately verify query semantics.
    """
    counts = {entry["name"]: entry["rows"] for entry in exports}
    overview = client.query_frame(
        query_path("overview").read_text(encoding="utf-8"), parameters
    ).iloc[0]
    distribution = client.query_frame(
        query_path("behavior_distribution").read_text(encoding="utf-8"), parameters
    )
    daily = client.query_frame(
        query_path("daily_active").read_text(encoding="utf-8"), parameters
    )
    weekly = client.query_frame(
        query_path("weekly_active").read_text(encoding="utf-8"), parameters
    )
    funnel = client.query_frame(
        query_path("strict_funnel").read_text(encoding="utf-8"), parameters
    ).iloc[0]
    repurchase_valid = True
    for frame in client.iter_frames(
        query_path("item_repurchase").read_text(encoding="utf-8"), parameters
    ):
        repurchase_valid &= bool(
            (
                frame["repeat_buyers"].between(0, frame["eligible_buyers"])
                & frame["eligible_buyers"].le(frame["observed_buyers"])
                & (
                    frame["repeat_user_rate_7d"].between(0, 1)
                    | (
                        frame["eligible_buyers"].eq(0)
                        & frame["repeat_user_rate_7d"].isna()
                    )
                )
            ).all()
        )
    return {
        "overview_rows": int(overview["events"]) == expected_rows,
        "behavior_total": int(distribution["events"].sum()) == expected_rows,
        "behavior_shares": abs(float(distribution["event_share"].sum()) - 1) < 1e-12,
        "daily_total": int(daily["events"].sum()) == expected_rows,
        "weekly_total": int(weekly["events"].sum()) == expected_rows,
        "all_events_sequenced": counts["user_sequences"] == expected_rows,
        "all_users_segmented": counts["user_proxy_segments"] == int(overview["users"]),
        "funnel_conserves_cohort": (
            int(funnel["eligible_view_pairs"]) + int(funnel["right_censored_pairs"])
            == int(funnel["observed_view_pairs"])
        ),
        "strict_funnel_monotonic": bool(
            funnel["eligible_view_pairs"]
            >= funnel["cart_pairs"]
            >= funnel["favorite_pairs"]
            >= funnel["purchase_pairs"]
            >= 0
        ),
        "repurchase_denominators": repurchase_valid,
    }


def benchmark_indexes(
    client: SQLiteClient, parameters: dict[str, SqlValue]
) -> tuple[dict[str, list[str]], list[IndexTrial]]:
    """Observe identical count queries with and without planner-selected indexes.

    Args:
        client: Complete read-only database.
        parameters: Observation interval parameters.

    Returns:
        EXPLAIN plans and two alternating trials per query/mode. Cache is uncontrolled.
    """
    values = dict(parameters)
    values["example_user"] = str(
        client.query_frame("SELECT user_id FROM users ORDER BY user_id LIMIT 1").iloc[
            0, 0
        ]
    )
    values["example_item"] = str(
        client.query_frame("SELECT item_id FROM items ORDER BY item_id LIMIT 1").iloc[
            0, 0
        ]
    )
    predicates = {
        "user_time": "user_id = :example_user AND event_time >= :start_time",
        "item_behavior": "item_id = :example_item AND behavior_type = 4",
        "time_range": (
            "event_time >= :start_time AND event_time < datetime(:start_time, '+1 day')"
        ),
    }
    plans: dict[str, list[str]] = {}
    trials: list[IndexTrial] = []
    for name, predicate in predicates.items():
        base = "SELECT COUNT(*) AS matches FROM behaviors"
        sql = base + " WHERE " + predicate
        plan = client.query_frame("EXPLAIN QUERY PLAN " + sql, values)
        plans[name] = plan["detail"].astype(str).tolist()
        matched: int | None = None
        for repeat in (1, 2):
            order = ("indexed", "scan") if repeat == 1 else ("scan", "indexed")
            for mode in order:
                statement = (
                    base
                    + (" NOT INDEXED" if mode == "scan" else "")
                    + " WHERE "
                    + predicate
                )
                start = time.perf_counter()
                count = int(cast(int, client.query_frame(statement, values).iloc[0, 0]))
                if matched is not None and count != matched:
                    raise RuntimeError("Indexed and scan count results differ")
                matched = count
                trials.append(
                    {
                        "lookup": name,
                        "mode": mode,
                        "repeat": repeat,
                        "rows_matched": count,
                        "seconds": round(time.perf_counter() - start, 6),
                    }
                )
    return plans, trials
