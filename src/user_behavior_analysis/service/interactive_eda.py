"""Recompute every core EDA module for date, cohort and category selections."""

from collections import Counter
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.dashboard_repository import aggregate_records
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.models.dashboard_models import DashboardFilter
from user_behavior_analysis.service.interactive_forward import forward_statistics
from user_behavior_analysis.service.interactive_paths import path_statistics
from user_behavior_analysis.service.interactive_paths import transition_statistics
from user_behavior_analysis.service.wide_contracts import require_contract

COHORTS = {
    "all": "TRUE",
    "low_activity": "key_count<10",
    "high_activity": "key_count>=50",
    "new_observed": "first_observed>=end_time-INTERVAL 3 DAY",
    "high_value_proxy": "buy_recency<=168 AND purchase_days>=2",
    "potential_proxy": "NOT high_value AND recency<=72",
    "at_risk_proxy": "NOT high_value AND recency>72 AND recency<=168",
    "dormant_proxy": "NOT high_value AND recency>168",
}


def validate_dashboard_filter(values: dict[str, str]) -> DashboardFilter:
    """Reject malformed filters while keeping all SQL values parameterized.

    Args:
        values: Requested dates and optional whitelisted global filters.

    Returns:
        Validated fixed-length source interval and exact identifiers.

    Raises:
        ValueError: Dates, cohort or identifier bounds are invalid.
    """
    require_contract(
        set(values) <= {"start", "end", "cohort", "category", "item"}, "Unknown filter"
    )
    require_contract({"start", "end"} <= set(values), "Missing dates")
    start, end = date.fromisoformat(values["start"]), date.fromisoformat(values["end"])
    require_contract(start <= end and (end - start).days <= 30, "Select one to 31 days")
    require_contract(values.get("cohort", "all") in COHORTS, "Unknown cohort")
    require_contract(
        all(len(values.get(name, "")) <= 100 for name in ("category", "item")),
        "Identifier too long",
    )
    return DashboardFilter(
        start.isoformat(),
        end.isoformat(),
        values.get("cohort", "all"),
        values.get("category", ""),
        values.get("item", ""),
    )


def _filter_source(
    connection: duckdb.DuckDBPyConnection, request: DashboardFilter
) -> pd.Timestamp:
    """Define cohorts on all categories in the selected historical window first.

    Args:
        connection: Immutable key_hour source registered as source.
        request: Global date/population/category and optional item controls.

    Returns:
        Exclusive source-calendar interval end.
    """
    end = pd.Timestamp(request.end) + pd.Timedelta(days=1)
    connection.execute(
        (
            "CREATE TEMP TABLE window_all AS SELECT * FROM"
            + " source WHERE event_time>=? AND event_time<?"
        ),
        [request.start, end.to_pydatetime()],
    )
    connection.execute(
        (
            "CREATE TEMP TABLE population AS WITH totals A"
            + "S (SELECT user_id,COUNT(*) AS key_count,"
        )
        + (
            "COUNT(DISTINCT CAST(event_time AS DATE)) FILT"
            + "ER(WHERE behavior_type=4) AS purchase_days,"
        )
        + (
            "date_diff('hour',MAX(event_time) FILTER(WHERE"
            + " behavior_type=4),?::TIMESTAMP) AS buy_recenc"
            + "y,"
        )
        + (
            "date_diff('hour',MAX(event_time),?::TIMESTAMP"
            + ") AS recency FROM window_all GROUP BY user_id"
            + "),"
        )
        + (
            "firsts AS (SELECT user_id,MIN(event_time) AS "
            + "first_observed FROM source GROUP BY user_id) "
        )
        + "SELECT t.*,f.first_observed,?::TIMESTAMP AS end_time,"
        + "COALESCE(buy_recency<=168 AND purchase_days>=2,FALSE) AS high_value "
        + "FROM totals t JOIN firsts f USING(user_id)",
        [end.to_pydatetime()] * 3,
    )
    connection.execute(
        (
            "CREATE TEMP TABLE filtered AS SELECT w.* FROM"
            + " window_all w JOIN population p USING(user_id"
            + ") WHERE "
        )
        + COHORTS[request.cohort]
        + (" AND (?='' OR category_id=?) AND (?='' OR ite" + "m_id=?)"),
        [request.category, request.category, request.item, request.item],
    )
    return end


def _overview(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Reconcile record weights and pair/user denominators for the active filters.

    Args:
        connection: Full filtered source.

    Returns:
        Core scale, depth and contemporaneous purchase measures.
    """
    return aggregate_records(
        connection,
        (
            "SELECT COALESCE(SUM(raw_count),0)::BIGINT AS "
            + "records,COUNT(*) AS four_tuple_keys,"
        )
        + "COUNT(DISTINCT user_id) AS users,COUNT(DISTINCT item_id) AS items,"
        + "COUNT(DISTINCT category_id) AS categories,"
        + "COUNT(DISTINCT user_id) FILTER(WHERE behavior_type=4) AS buying_users,"
        + (
            "COUNT(DISTINCT(user_id,item_id)) FILTER(WHERE"
            + " behavior_type=4) AS buying_pairs,"
        )
        + (
            "COALESCE(SUM(raw_count) FILTER(WHERE behavior"
            + "_type=4),0)::BIGINT AS buy_records,"
        )
        + "COUNT(DISTINCT(user_id,event_time)) AS observed_user_hours,"
        + (
            "COUNT(DISTINCT(user_id,CAST(event_time AS DAT"
            + "E))) AS active_user_days FROM filtered"
        ),
    )[0]


def _entity_statistics(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Calculate pair support before ranking items or categories.

    Args:
        connection: Filtered source data.

    Returns:
        Full category data, supported item rankings and an explicit scatter subset.
    """
    connection.execute(
        (
            "CREATE TEMP TABLE pairs AS SELECT user_id,ite"
            + "m_id,category_id,SUM(raw_count)::BIGINT AS re"
            + "cords,"
        )
        + (
            "COALESCE(SUM(raw_count) FILTER(WHERE behavior"
            + "_type=1),0)::BIGINT AS pv_records,"
        )
        + (
            "COALESCE(SUM(raw_count) FILTER(WHERE behavior"
            + "_type=4),0)::BIGINT AS buy_records,"
        )
        + (
            "COALESCE(SUM(raw_count) FILTER(WHERE behavior"
            + "_type=2),0)::BIGINT AS fav_records,"
        )
        + (
            "COALESCE(SUM(raw_count) FILTER(WHERE behavior"
            + "_type=3),0)::BIGINT AS cart_records,"
        )
        + (
            "COUNT(*) FILTER(WHERE behavior_type=1)>0 AS p"
            + "v,COUNT(*) FILTER(WHERE behavior_type=4)>0 AS"
            + " buy "
        )
        + "FROM filtered GROUP BY user_id,item_id,category_id"
    )
    for entity in ("item", "category"):
        name = entity + "_id"
        connection.execute(
            "CREATE TEMP TABLE "
            + entity
            + "_totals AS SELECT "
            + name
            + (",MAX(category_id) AS category_id" if entity == "item" else "")
            + (
                ",SUM(records)::BIGINT AS records,SUM(pv_recor"
                + "ds)::BIGINT AS pv_records,SUM(buy_records)::B"
                + "IGINT AS buy_records,"
            )
            + (
                "COUNT(*) FILTER(WHERE pv) AS viewed_pairs,COU"
                + "NT(*) FILTER(WHERE pv AND buy) AS covered_pai"
                + "rs,"
            )
            + (
                "COUNT(*) FILTER(WHERE buy) AS buying_pairs,CO"
                + "UNT(*) FILTER(WHERE pv AND buy)::DOUBLE/"
            )
            + (
                "NULLIF(COUNT(*) FILTER(WHERE pv),0) AS purcha"
                + "se_coverage FROM pairs GROUP BY "
            )
            + name
        )
    thresholds = aggregate_records(
        connection,
        (
            "SELECT median(pv_records) AS pv_records,media"
            + "n(purchase_coverage) AS purchase_coverage FRO"
            + "M item_totals WHERE viewed_pairs>=20"
        ),
    )[0]
    return {
        "quadrant_thresholds": thresholds,
        "total_pairs": require_result_row(
            connection.execute("SELECT COUNT(*) FROM pairs").fetchone()
        )[0],
        "categories": aggregate_records(
            connection, ("SELECT * FROM category_totals ORDER BY record" + "s DESC")
        ),
        "items_volume": aggregate_records(
            connection,
            ("SELECT * FROM item_totals ORDER BY records DE" + "SC,item_id LIMIT 20"),
        ),
        "items_conversion": aggregate_records(
            connection,
            (
                "SELECT * FROM item_totals WHERE viewed_pairs>"
                + "=50 ORDER BY purchase_coverage DESC,viewed_pa"
                + "irs DESC,item_id LIMIT 20"
            ),
        ),
        "item_quadrants": aggregate_records(
            connection,
            (
                "SELECT * FROM item_totals WHERE viewed_pairs>"
                + "=20 ORDER BY pv_records DESC,item_id LIMIT 15"
                + "00"
            ),
        ),
        "scatter_scope": (
            "At least 20 viewed pairs; up to 1500 items or" + "dered by pv records."
        ),
    }


def query_dashboard(
    request: DashboardFilter, source_path: Path | None = None
) -> dict[str, Any]:
    """Recompute every core panel on one consistent filtered population.

    Args:
        request: Validated global controls.
        source_path: Optional project-contained fixture or immutable key-hour file.

    Returns:
        Complete aggregate payload; no hidden row sampling replaces core statistics.
    """
    source_path = project_output_path(
        source_path or Path("data/processed/base_raw_v2/key_hour/data.parquet")
    )
    temporary = project_output_path(".cache/eda_live/spill")
    temporary.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as connection:
        connection.execute("SET memory_limit='768MB'")
        connection.execute("SET threads=2")
        connection.execute("SET preserve_insertion_order=false")
        connection.execute("SET temp_directory=?", [str(temporary)])
        connection.read_parquet(str(source_path)).create_view("source")
        bounds = require_result_row(
            connection.execute(
                ("SELECT MIN(event_time),MAX(event_time) FROM s" + "ource")
            ).fetchone()
        )
        require_contract(bounds is not None and bounds[0] is not None, "Empty source")
        require_contract(
            pd.Timestamp(request.start) >= pd.Timestamp(bounds[0]).normalize()
            and pd.Timestamp(request.end) <= pd.Timestamp(bounds[1]).normalize(),
            "Dates outside observed source",
        )
        end = _filter_source(connection, request)
        result: dict[str, Any] = {
            "filters": asdict(request),
            "overview": _overview(connection),
        }
        result["behaviors"] = aggregate_records(
            connection,
            (
                "SELECT behavior_type,SUM(raw_count)::BIGINT A"
                + "S records FROM filtered GROUP BY behavior_typ"
                + "e ORDER BY behavior_type"
            ),
        )
        result["daily"] = aggregate_records(
            connection,
            (
                "SELECT CAST(event_time AS DATE)::VARCHAR AS d"
                + "ay,behavior_type,SUM(raw_count)::BIGINT AS re"
                + "cords,COUNT(DISTINCT user_id) AS users FROM f"
                + "iltered GROUP BY day,behavior_type ORDER BY d"
                + "ay,behavior_type"
            ),
        )
        result["daily_coverage"] = aggregate_records(
            connection,
            (
                "SELECT CAST(event_time AS DATE)::VARCHAR AS d"
                + "ay,COUNT(DISTINCT user_id) AS users,COUNT(DIS"
                + "TINCT user_id) FILTER(WHERE behavior_type=4) "
                + "AS buying_users FROM filtered GROUP BY day OR"
                + "DER BY day"
            ),
        )
        result["hour_coverage"] = aggregate_records(
            connection,
            (
                "SELECT isodow(event_time)-1 AS weekday,hour(e"
                + "vent_time) AS hour,COUNT(DISTINCT user_id) AS"
                + " users,COUNT(DISTINCT user_id) FILTER(WHERE b"
                + "ehavior_type=4) AS buying_users FROM filtered"
                + " GROUP BY weekday,hour"
            ),
        )
        result["heatmap"] = aggregate_records(
            connection,
            (
                "SELECT isodow(event_time)-1 AS weekday,hour(e"
                + "vent_time) AS hour,behavior_type,SUM(raw_coun"
                + "t)::BIGINT AS records,COUNT(DISTINCT user_id)"
                + " AS users FROM filtered GROUP BY weekday,hour"
                + ",behavior_type"
            ),
        )
        dates = pd.date_range(request.start, request.end)
        result["weekday_days"] = dict(Counter(int(value.weekday()) for value in dates))
        result["user_distribution"] = aggregate_records(
            connection,
            (
                "SELECT CASE WHEN records<10 THEN '1-9' WHEN r"
                + "ecords<50 THEN '10-49' WHEN records<200 THEN "
                + "'50-199' WHEN records<1000 THEN '200-999' ELS"
                + "E '1000+' END AS bin,COUNT(*) AS users,SUM(bu"
                + "y)::BIGINT AS buying_users FROM (SELECT user_"
                + "id,SUM(raw_count) AS records,MAX((behavior_ty"
                + "pe=4)::INTEGER) AS buy FROM filtered GROUP BY"
                + " user_id) GROUP BY bin"
            ),
        )
        result["activity_exact"] = aggregate_records(
            connection,
            (
                "SELECT records,COUNT(*) AS users FROM (SELECT"
                + " user_id,SUM(raw_count)::BIGINT AS records FR"
                + "OM filtered GROUP BY user_id) GROUP BY record"
                + "s ORDER BY records"
            ),
        )
        result["purchase_distribution"] = aggregate_records(
            connection,
            (
                "SELECT buy_records,COUNT(*) AS users FROM (SE"
                + "LECT user_id,COALESCE(SUM(raw_count) FILTER(W"
                + "HERE behavior_type=4),0)::BIGINT AS buy_recor"
                + "ds FROM filtered GROUP BY user_id) GROUP BY b"
                + "uy_records ORDER BY buy_records"
            ),
        )
        result.update(_entity_statistics(connection))
        result["funnel"] = path_statistics(connection, end)
        result["transitions"] = transition_statistics(connection)
        result["forward"] = forward_statistics(connection, end)
        result["preferences"] = aggregate_records(
            connection,
            (
                "SELECT * FROM (SELECT CASE WHEN u.key_count<1"
                + "0 THEN '低活跃' WHEN u.key_count<50 THEN '中活跃' W"
                + "HEN u.key_count<200 THEN '高活跃' ELSE '极高活跃' EN"
                + "D AS activity,category_id,COUNT(*) AS keys,RO"
                + "W_NUMBER() OVER(PARTITION BY activity ORDER B"
                + "Y COUNT(*) DESC,category_id) AS rank FROM fil"
                + "tered p JOIN population u USING(user_id) GROU"
                + "P BY activity,category_id) WHERE rank<=5 ORDE"
                + "R BY activity,rank"
            ),
        )
    return result
