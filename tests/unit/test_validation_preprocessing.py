"""Verify frozen preprocessing, group accounting and exact evaluation metrics."""

import unittest
from dataclasses import asdict

import duckdb
import numpy as np
import pandas as pd

from user_behavior_analysis.models.validation_models import FeatureTransform
from user_behavior_analysis.service.validation_experiments import _apply_fallback
from user_behavior_analysis.service.validation_groups import cohort_masks
from user_behavior_analysis.service.validation_metrics import _weighted_rank_auc
from user_behavior_analysis.service.validation_metrics import prediction_metrics
from user_behavior_analysis.service.validation_preprocessing import (
    fit_transform_contract,
)
from user_behavior_analysis.service.validation_preprocessing import training_profiles
from user_behavior_analysis.service.validation_preprocessing import transform_frame
from user_behavior_analysis.service.validation_selection import _eligible_profile


class ValidationPreprocessingTests(unittest.TestCase):
    """Keep future rows from changing training state or selection rules."""

    def test_unknown_category_uses_its_own_bucket(self) -> None:
        """Do not extend the learned vocabulary with a future category."""
        # Arrange
        state = FeatureTransform(["kind"], {}, {}, {}, {"kind": ["a"]}, [])
        # Act
        result = transform_frame(
            pd.DataFrame({"kind": ["future", "a"]}), state
        ).toarray()
        # Assert
        np.testing.assert_array_equal(result, [[1, 0], [0, 1]])

    def test_future_values_do_not_refit_scaling(self) -> None:
        """Keep medians and moments unchanged after future extremes."""
        # Arrange
        state = FeatureTransform(
            ["number"], {"number": 2}, {"number": 2}, {"number": 1}, {}, ["number"]
        )
        before = asdict(state)
        # Act
        transform_frame(pd.DataFrame({"number": [1e6, np.nan]}), state)
        # Assert
        self.assertEqual(before, asdict(state))

    def test_missing_indicator_distinguishes_imputation(self) -> None:
        """Retain missingness separately from an observed training median."""
        # Arrange
        state = FeatureTransform(
            ["number"], {"number": 2}, {"number": 2}, {"number": 1}, {}, ["number"]
        )
        # Act
        result = transform_frame(pd.DataFrame({"number": [2, np.nan]}), state).toarray()
        # Assert
        np.testing.assert_array_equal(result, [[0, 0], [0, 1]])

    def test_training_moments_account_for_imputed_rows(self) -> None:
        """Use complete training rows for the imputed numeric distribution."""
        # Arrange
        with duckdb.connect() as connection:
            connection.execute(
                (
                    "CREATE TABLE train AS SELECT * FROM (VALUES (1.0),"
                    + "(3.0),(NULL))v(number)"
                )
            )
            definitions = [{"name": "number", "dtype": "float64"}]
            profiles = training_profiles(connection, definitions)
            # Act
            state = fit_transform_contract(connection, profiles, ["number"])
        # Assert
        self.assertAlmostEqual(state.means["number"], 2)
        self.assertAlmostEqual(state.scales["number"], np.sqrt(2 / 3))

    def test_protected_constant_is_not_a_fake_signal(self) -> None:
        """Record a constant's business meaning without claiming learnability."""
        # Arrange
        profile = {"nonnull": 10, "dtype": "int64", "variance": 0, "protected": True}
        # Act
        keep, reason = _eligible_profile(profile, {})
        # Assert
        self.assertFalse(keep)
        self.assertIn("constant", reason)

    def test_single_class_auc_is_unavailable(self) -> None:
        """Do not publish invented AUC for a cohort lacking purchases."""
        # Arrange / Act
        result = prediction_metrics(np.zeros(3), np.array([0.1, 0.2, 0.3]))
        # Assert
        self.assertIsNone(result["roc_auc"])

    def test_bootstrap_auc_handles_score_ties(self) -> None:
        """Allocate half credit to a tied positive-negative comparison."""
        # Arrange / Act
        result = _weighted_rank_auc(np.array([0, 1]), np.ones(2), np.array([0]))
        # Assert
        self.assertEqual(result, 0.5)

    def test_unavailable_svd_falls_back_without_using_target(self) -> None:
        """Choose historical coverage flags rather than future labels."""
        # Arrange
        predictions = {
            name: np.array([value])
            for name, value in {
                "business": 0.2,
                "svd": 0.9,
                "cooccurrence": 0.8,
                "sequence": 0.3,
                "combined": 0.7,
            }.items()
        }
        frame = pd.DataFrame({"pair_svd_available": [0], "pair_cooc_graph_known": [0]})
        # Act
        _apply_fallback(predictions, frame)
        # Assert
        self.assertEqual(predictions["svd"][0], 0.2)

    def test_cohorts_do_not_depend_on_future_labels(self) -> None:
        """Keep activity and coverage cohorts label-independent."""
        # Arrange
        frame = pd.DataFrame(
            {
                "user_activity_level_7d": [0, 3],
                "user_observed_age_days": [2, 10],
                "pair_svd_available": [0, 1],
                "pair_cooc_graph_known": [0, 1],
                "target": [0, 1],
            }
        )
        before = cohort_masks(frame)
        # Act
        frame["target"] = [1, 0]
        after = cohort_masks(frame)
        # Assert
        self.assertTrue(
            all(np.array_equal(value, after[name]) for name, value in before.items())
        )


if __name__ == "__main__":
    unittest.main()
