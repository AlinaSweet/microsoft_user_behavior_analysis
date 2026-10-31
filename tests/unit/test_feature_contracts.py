"""Check feature definitions and sparse interaction contracts independently."""

import unittest

import numpy as np
import pandas as pd

from user_behavior_analysis.service.feature_explanations import explain_feature
from user_behavior_analysis.service.feature_explanations import feature_window_label
from user_behavior_analysis.service.feature_latent_fit import interaction_matrix
from user_behavior_analysis.service.feature_registry import ENTITY_KEYS
from user_behavior_analysis.service.feature_registry import derived_feature_definitions
from user_behavior_analysis.service.feature_registry import window_feature_definitions
from user_behavior_analysis.service.feature_snapshots import snapshot_parameters

WEIGHTS = {"pv": 1, "fav": 2, "cart": 3, "buy": 4}


class FeatureContractTests(unittest.TestCase):
    """Exercise one registry, boundary or sparse-matrix scenario per case."""

    def test_field_specific_window_is_not_shown_as_missing_days(self) -> None:
        """Keep unspecified fixed lengths readable in the published dictionary."""
        # Arrange / Act
        result = feature_window_label(None)
        # Assert
        self.assertEqual(result, "按字段定义的历史或截点")

    def test_latent_formula_explains_frozen_projection(self) -> None:
        """Expose fitted components and normalization in coordinate definitions."""
        # Arrange / Act
        result = explain_feature("user_svd_03", "frozen latent projection")
        # Assert
        self.assertIn("IDF", result)
        self.assertIn("components_.T", result)

    def test_association_formula_explains_its_denominator(self) -> None:
        """Resolve an intermediate alias to the actual rule confidence ratio."""
        # Arrange / Act
        result = explain_feature(
            "pair_cooc_rule_mean_confidence", "COALESCE(m.mean_confidence,0)"
        )
        # Assert
        self.assertIn("共同用户数/源商品用户数", result)

    def test_registered_scalar_names_are_globally_unique(self) -> None:
        """Keep entity prefixes distinct across all statistical windows."""
        # Arrange
        definitions = [
            row
            for entity in ENTITY_KEYS
            for row in window_feature_definitions(entity, [1, 3, 7, 30])
            + derived_feature_definitions(entity, WEIGHTS)
        ]
        # Act
        names = [row["name"] for row in definitions]
        # Assert
        self.assertEqual(len(names), len(set(names)))

    def test_windows_cross_month_boundaries(self) -> None:
        """Subtract calendar days from the exclusive cutoff exactly."""
        # Arrange / Act
        parameters = snapshot_parameters("2025-12-01", [1, 3, 7, 30])
        # Assert
        self.assertEqual(str(parameters["start_7"]), "2025-11-24 00:00:00")
        self.assertEqual(str(parameters["start_30"]), "2025-11-01 00:00:00")

    def test_unknown_items_are_excluded_from_frozen_matrix(self) -> None:
        """Keep unknown interactions in coverage denominators only."""
        # Arrange
        frame = pd.DataFrame(
            {
                "user_id": ["u1", "u1"],
                "item_id": ["known", "new"],
                "pair_pv_key_count_7d": [2, 3],
                "pair_fav_key_count_7d": [0, 0],
                "pair_cart_key_count_7d": [0, 0],
                "pair_buy_key_count_7d": [1, 0],
            }
        )
        # Act
        matrix, known, total = interaction_matrix(
            frame, pd.Index(["u1"]), pd.Index(["known"]), WEIGHTS
        )
        # Assert
        self.assertAlmostEqual(float(matrix[0, 0]), float(np.log1p(6)), places=6)
        self.assertEqual(known.tolist(), [1])
        self.assertEqual(total.tolist(), [2])

    def test_targets_are_absent_from_registry(self) -> None:
        """Exclude future outcomes from historical feature definitions."""
        # Arrange
        definitions = window_feature_definitions("user", [1, 3, 7, 30])
        # Act
        names = [row["name"] for row in definitions]
        # Assert
        self.assertFalse(any("target" in name for name in names))


if __name__ == "__main__":
    unittest.main()
