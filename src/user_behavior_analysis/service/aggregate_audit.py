"""Independently reconstruct every aggregate cell using Dask global operations."""

from pathlib import Path
from typing import TypedDict
from typing import cast

import dask.dataframe as dd
import pandas as pd

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.service.runtime import resource_plan
from user_behavior_analysis.service.runtime import start_client

COUNT_FIELDS = ["event_count", "pv_count", "fav_count", "cart_count", "buy_count"]
AUDIT_DEFINITIONS = {
    "user_daily_stats": (
        ["user_id", "event_date"],
        [("item_id", "unique_items")],
        True,
    ),
    "item_daily_stats": (
        ["item_id", "event_date"],
        [("user_id", "unique_users")],
        True,
    ),
    "time_hourly_stats": (
        ["event_time"],
        [("user_id", "unique_users"), ("item_id", "unique_items")],
        False,
    ),
}


class AggregateValueAudit(TypedDict):
    """Record global grouping counts and full outer-join value differences."""

    name: str
    status: str
    expected_groups: int
    mismatched_rows: int
    compared_columns: list[str]
    checks: dict[str, bool]


def _expected_table(frame: dd.DataFrame, name: str) -> dd.DataFrame:
    keys, uniqueness, bounds = AUDIT_DEFINITIONS[name]
    expected = frame.groupby(keys)[COUNT_FIELDS].sum(split_out=16).reset_index()
    if bounds:
        times = (
            frame.groupby(keys)["event_time"]
            .agg(["min", "max"], split_out=16)
            .reset_index()
            .rename(columns={"min": "first_event_time", "max": "last_event_time"})
        )
        expected = expected.merge(times, on=keys, how="inner")
    for column, target in uniqueness:
        unique = frame[[*keys, column]].drop_duplicates(split_out=16)
        counts = (
            unique.groupby(keys).size(split_out=16).to_frame(name=target).reset_index()
        )
        expected = expected.merge(counts, on=keys, how="inner")
    return cast(dd.DataFrame, expected)


def _partition_mismatches(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    valid = frame["_merge"].astype("string").eq("both")
    for column in columns:
        left = frame[column + "_expected"]
        right = frame[column + "_actual"]
        if column.endswith("_time"):
            same = pd.to_datetime(left).eq(pd.to_datetime(right))
        else:
            same = left.eq(right)
        valid &= same.fillna(False)
    return pd.Series([int((~valid).sum())], name="mismatches", dtype="int64")


def audit_aggregate_values(
    config: ProjectConfig, event_directory: Path, aggregate_directory: Path
) -> list[AggregateValueAudit]:
    """Recompute all count, distinct, and time-bound cells independently.

    Args:
        config: Existing bounded Dask cluster settings.
        event_directory: Complete compact event relation.
        aggregate_directory: User/day, item/day, and hour output directories.

    Returns:
        Whole-table comparisons using global groups and full outer joins.

    Notes:
        Expected relations are rebuilt from events. Aggregate totals are not
        used as substitutes for comparing every group and measure.
    """
    source_path = project_output_path(event_directory)
    aggregate_path = project_output_path(aggregate_directory)
    frame = dd.read_parquet(
        str(source_path), columns=["user_id", "item_id", "behavior_type", "event_time"]
    )
    frame = frame.assign(
        event_date=frame["event_time"].dt.floor("D").astype("datetime64[ms]"),
        event_count=1,
        pv_count=(frame["behavior_type"] == 1).astype("uint64"),
        fav_count=(frame["behavior_type"] == 2).astype("uint64"),
        cart_count=(frame["behavior_type"] == 3).astype("uint64"),
        buy_count=(frame["behavior_type"] == 4).astype("uint64"),
    )
    results: list[AggregateValueAudit] = []
    with start_client(config, resource_plan(config)) as client:
        for name, (keys, _, _) in AUDIT_DEFINITIONS.items():
            expected = _expected_table(frame, name)
            actual = dd.read_parquet(str(aggregate_path / name))
            if "event_date" in keys:
                actual = actual.assign(
                    event_date=dd.to_datetime(actual["event_date"]).astype(
                        "datetime64[ms]"
                    )
                )
            columns = [column for column in expected.columns if column not in keys]
            same_schema = set(actual.columns) == set(expected.columns)
            if not same_schema:
                results.append(
                    {
                        "name": name,
                        "status": "failed",
                        "expected_groups": -1,
                        "mismatched_rows": -1,
                        "compared_columns": columns,
                        "checks": {"schema_columns": False},
                    }
                )
                continue
            joined = expected.merge(
                actual,
                on=keys,
                how="outer",
                indicator=True,
                suffixes=("_expected", "_actual"),
            )
            mismatches = joined.map_partitions(
                _partition_mismatches,
                columns,
                meta=pd.Series(dtype="int64", name="mismatches"),
            ).sum()
            group_count, mismatch_count = client.gather(
                client.compute([expected.shape[0], mismatches])
            )
            results.append(
                {
                    "name": name,
                    "status": "passed" if int(mismatch_count) == 0 else "failed",
                    "expected_groups": int(group_count),
                    "mismatched_rows": int(mismatch_count),
                    "compared_columns": columns,
                    "checks": {
                        "schema_columns": True,
                        "every_group_value": int(mismatch_count) == 0,
                    },
                }
            )
    return results
