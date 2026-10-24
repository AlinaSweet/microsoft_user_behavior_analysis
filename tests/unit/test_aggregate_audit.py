"""Verify that balanced aggregate corruption cannot pass cell comparisons."""

import unittest

import dask.dataframe as dd
import pandas as pd
from distributed import Client

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.service.aggregate_audit import _compare_table
from user_behavior_analysis.service.aggregate_audit import _expected_table
from user_behavior_analysis.service.aggregate_audit import _partition_mismatches


class AggregateComparisonTests(unittest.TestCase):
    """Verify comparison behavior independently of group construction."""

    def test_balanced_corruption_is_detected(self) -> None:
        """Detect per-group errors even when a grand total is unchanged."""
        # Arrange
        frame = pd.DataFrame(
            {
                "_merge": ["both", "both"],
                "event_count_expected": [3, 2],
                "event_count_actual": [4, 1],
            }
        )
        # Act
        result = _partition_mismatches(frame, ["event_count"])
        # Assert
        self.assertEqual(int(result.sum()), 2)

    def test_daily_slicing_detects_an_extra_persisted_date(self) -> None:
        """Detect an extra day even when it has no source events."""
        # Arrange
        timestamp = pd.to_datetime(["2025-11-18 00"]).astype("datetime64[ms]")
        frame = dd.from_pandas(
            pd.DataFrame(
                {
                    "user_id": ["001"],
                    "item_id": ["01"],
                    "event_time": timestamp,
                    "event_date": timestamp,
                    "event_count": [1],
                    "pv_count": [1],
                    "fav_count": [0],
                    "cart_count": [0],
                    "buy_count": [0],
                }
            ),
            npartitions=1,
        )
        expected = _expected_table(frame, "item_daily_stats").compute()
        actual = dd.from_pandas(
            pd.concat(
                [
                    expected,
                    expected.assign(
                        event_date=expected["event_date"] + pd.Timedelta(days=1)
                    ),
                ],
                ignore_index=True,
            ),
            npartitions=1,
        )
        actual = actual.assign(event_date=actual["event_date"].astype("datetime64[ms]"))
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        # Act
        with Client(
            processes=False,
            n_workers=1,
            threads_per_worker=1,
            dashboard_address=None,
            local_directory=str(scratch),
        ) as client:
            groups, differences = _compare_table(
                client, frame, actual, "item_daily_stats"
            )
        # Assert
        self.assertEqual((groups, differences), (1, 1))
