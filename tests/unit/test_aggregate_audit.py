"""Verify that balanced aggregate corruption cannot pass cell comparisons."""

import unittest

import pandas as pd

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
