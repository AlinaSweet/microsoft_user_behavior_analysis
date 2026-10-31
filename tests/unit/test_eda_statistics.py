"""Check descriptive EDA denominators and bin boundaries."""

import unittest

import numpy as np
import pandas as pd

from user_behavior_analysis.service.eda_statistics import summarize_bins
from user_behavior_analysis.service.eda_statistics import wilson_interval


class EDAStatisticsTests(unittest.TestCase):
    """Test independent numerical scenarios for the published EDA helpers."""

    def test_zero_support_is_unavailable(self) -> None:
        """Keep an unobserved cohort different from a zero purchase rate."""
        # Arrange / Act
        lower, upper = wilson_interval(0, 0)
        # Assert
        self.assertTrue(bool(np.isnan(lower)))
        self.assertTrue(bool(np.isnan(upper)))

    def test_wilson_interval_matches_known_half_success_case(self) -> None:
        """Verify both endpoints against an independently calculated value."""
        # Arrange / Act
        lower, upper = wilson_interval(5, 10)
        # Assert
        self.assertAlmostEqual(float(lower), 0.2365895947, places=8)
        self.assertAlmostEqual(float(upper), 0.7634104053, places=8)

    def test_bin_lower_bound_is_included(self) -> None:
        """Assign the threshold itself to the following left-closed bin."""
        # Arrange
        frame = pd.DataFrame({"count": [0, 1, 2, 3], "target": [0, 1, 1, 0]})
        # Act
        result = summarize_bins(frame, "count", "target", [0, 1, 3, np.inf])
        # Assert
        self.assertEqual(result["users"].tolist(), [1, 2, 1])
        self.assertEqual(result["purchase_rate"].tolist(), [0.0, 1.0, 0.0])


if __name__ == "__main__":
    unittest.main()
