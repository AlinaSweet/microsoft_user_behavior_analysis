"""Exercise real globally filtered EDA on an isolated weighted source fixture."""

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.models.dashboard_models import DashboardFilter
from user_behavior_analysis.service.interactive_eda import query_dashboard
from user_behavior_analysis.service.interactive_eda import validate_dashboard_filter


class InteractiveEDATests(unittest.TestCase):
    """Check filter intersections, raw multiplicity and future-window boundaries."""

    def setUp(self) -> None:
        """Create a private key-frequency table with two categories and purchases."""
        cache = PROJECT_ROOT / ".cache/tests"
        cache.mkdir(parents=True, exist_ok=True)
        self.resources = ExitStack()
        self.addCleanup(self.resources.close)
        directory = self.resources.enter_context(tempfile.TemporaryDirectory(dir=cache))
        self.path = Path(directory) / "source.parquet"
        frame = pd.DataFrame(
            [
                ("u1", "a", "c1", "2025-11-18 00", 1, 3),
                ("u1", "a", "c1", "2025-11-18 01", 3, 1),
                ("u1", "a", "c1", "2025-11-18 02", 2, 1),
                ("u1", "a", "c1", "2025-11-18 03", 4, 1),
                ("u2", "b", "c2", "2025-11-19 00", 1, 2),
                ("u2", "b", "c2", "2025-11-26 00", 4, 1),
                ("u3", "z", "c2", "2025-12-18 23", 1, 1),
            ],
            columns=[
                "user_id",
                "item_id",
                "category_id",
                "event_time",
                "behavior_type",
                "raw_count",
            ],
        )
        frame["event_time"] = pd.to_datetime(frame.event_time)
        frame.to_parquet(self.path, index=False)

    def test_all_records_retain_same_key_weight(self) -> None:
        """Three same-hour logs remain three records and one key."""
        # Arrange / Act
        result = query_dashboard(DashboardFilter("2025-11-18", "2025-11-19"), self.path)
        # Assert
        self.assertEqual(result["overview"]["records"], 8)
        self.assertEqual(result["overview"]["four_tuple_keys"], 5)

    def test_category_updates_all_core_counts(self) -> None:
        """Apply category selection to daily data as well as summary cards."""
        # Arrange / Act
        result = query_dashboard(
            DashboardFilter("2025-11-18", "2025-11-19", category="c2"), self.path
        )
        # Assert
        self.assertEqual(result["overview"]["records"], 2)
        self.assertEqual(sum(r["records"] for r in result["daily"]), 2)

    def test_cohort_is_computed_before_category_filter(self) -> None:
        """Determine high activity globally even when the selected category is small."""
        # Arrange
        frame = pd.read_parquet(self.path)
        extra = pd.DataFrame(
            [
                {
                    "user_id": "u2",
                    "item_id": str(i),
                    "category_id": "c1",
                    "event_time": pd.Timestamp("2025-11-18"),
                    "behavior_type": 1,
                    "raw_count": 1,
                }
                for i in range(60)
            ]
        )
        pd.concat([frame, extra], ignore_index=True).to_parquet(self.path, index=False)
        # Act
        result = query_dashboard(
            DashboardFilter("2025-11-18", "2025-11-19", "high_activity", "c2"),
            self.path,
        )
        # Assert
        self.assertEqual(result["overview"]["records"], 2)

    def test_no_future_window_is_unknown(self) -> None:
        """Never show a zero conversion rate for unavailable follow-up."""
        # Arrange / Act
        result = query_dashboard(DashboardFilter("2025-12-18", "2025-12-18"), self.path)
        # Assert
        self.assertFalse(result["forward"]["available"])

    def test_strict_funnel_has_complete_followup(self) -> None:
        """Require ordered hours while retaining the mature seven-day horizon."""
        # Arrange / Act
        result = query_dashboard(DashboardFilter("2025-11-18", "2025-11-26"), self.path)
        # Assert
        self.assertEqual(result["funnel"]["stage_counts"], [2, 1, 1, 1])

    def test_invalid_date_order_is_rejected(self) -> None:
        """Reject an inverted global interval before running queries."""
        # Arrange / Act / Assert
        with self.assertRaises(ValueError):
            validate_dashboard_filter({"start": "2025-12-01", "end": "2025-11-18"})


if __name__ == "__main__":
    unittest.main()
