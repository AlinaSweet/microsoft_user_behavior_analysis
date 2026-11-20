"""Verify the three training treatments without using any holdout data."""

import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from user_behavior_analysis.dao.sampling_repository import load_sampling_settings
from user_behavior_analysis.service.sampling_strategies import prepare_training


class SamplingStrategyTests(unittest.TestCase):
    """Check deterministic class treatment and interpolated feature boundaries."""

    def setUp(self) -> None:
        """Build two distinct positive training points and eight distant negatives."""
        self.settings = replace(
            load_sampling_settings(Path("configs/stage3_sampling.json")),
            negative_per_positive=2,
        )
        self.values = np.array(
            [[0.0, 0.0], [1.0, 1.0]] + [[float(i), 2.0] for i in range(10, 18)],
            dtype=np.float32,
        )
        self.target = np.array([1, 1] + [0] * 8, dtype=np.int8)

    def test_smote_interpolates_between_positive_training_points(self) -> None:
        """Synthetic points remain within the two positive endpoints."""
        result = prepare_training("smote", self.values, self.target, self.settings)
        added = result.values[len(self.target) :]
        self.assertEqual(result.synthetic_rows, 2)
        np.testing.assert_array_equal(result.target[-2:], [1, 1])
        np.testing.assert_allclose(added[:, 0], added[:, 1])
        self.assertTrue(np.all((added > 0) & (added < 1)))

    def test_undersample_preserves_positives_and_draws_unique_negatives(self) -> None:
        """Sample precisely the configured number of original negatives."""
        result = prepare_training(
            "undersample", self.values, self.target, self.settings
        )
        np.testing.assert_array_equal(
            result.values[result.target == 1], self.values[:2]
        )
        selected = result.values[result.target == 0, 0]
        self.assertEqual(len(np.unique(selected)), 4)
        self.assertTrue(np.isin(selected, self.values[2:, 0]).all())

    def test_class_weight_keeps_rows_and_sets_target_class_mass(self) -> None:
        """Assign ratio-matched effective weights while retaining all ten rows."""
        result = prepare_training(
            "class_weight", self.values, self.target, self.settings
        )
        np.testing.assert_array_equal(result.target, self.target)
        np.testing.assert_array_equal(result.values, self.values)
        positive_mass, negative_mass = 2 * result.weights[1], 8 * result.weights[0]
        self.assertAlmostEqual(negative_mass / positive_mass, 2.0)
        self.assertAlmostEqual(positive_mass + negative_mass, len(self.target))


if __name__ == "__main__":
    unittest.main()
