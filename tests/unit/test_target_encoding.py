"""Verify user-held-out category encoding and frozen sparse projection semantics."""

import unittest
from dataclasses import asdict

import numpy as np
import pandas as pd

from user_behavior_analysis.service.sparse_embedding import sparse_categories
from user_behavior_analysis.service.target_encoding import encode_target
from user_behavior_analysis.service.target_encoding import fit_target_encoding
from user_behavior_analysis.service.target_encoding import user_fold


class TargetEncodingTests(unittest.TestCase):
    """Prevent own-user and future-label leakage in the actual encoding code."""

    def setUp(self) -> None:
        """Construct many grouped users sharing a few categories."""
        self.frame = pd.DataFrame(
            {
                "user_id": [f"u{i}" for i in range(100)],
                "category": ["a" if i % 2 else "b" for i in range(100)],
                "target": [int(i % 7 == 0) for i in range(100)],
            }
        )

    def test_own_user_label_cannot_change_own_encoded_value(self) -> None:
        """Exclude the user's complete fold and its labels from the prior too."""
        # Arrange
        before = fit_target_encoding(self.frame, "category", 5, 50, "2025-12-02")
        modified = self.frame.copy()
        modified.loc[0, "target"] = 1 - int(modified.target.iloc[0])
        # Act
        after = fit_target_encoding(modified, "category", 5, 50, "2025-12-02")
        # Assert
        self.assertEqual(
            encode_target(self.frame.iloc[:1], before, True)[0],
            encode_target(modified.iloc[:1], after, True)[0],
        )

    def test_unknown_category_uses_training_prior(self) -> None:
        """Do not invent a purchase rate for an unseen category."""
        # Arrange
        state = fit_target_encoding(self.frame, "category", 5, 50, "2025-12-02")
        future = pd.DataFrame({"category": ["unknown"]})
        # Act
        result = encode_target(future, state, False)
        # Assert
        self.assertAlmostEqual(
            float(result[0]), float(self.frame.target.mean()), places=7
        )

    def test_future_targets_are_ignored(self) -> None:
        """Validation targets cannot update a fitted mapping."""
        # Arrange
        state = fit_target_encoding(self.frame, "category", 5, 50, "2025-12-02")
        before = asdict(state)
        # Act
        encode_target(self.frame.assign(target=1), state, False)
        # Assert
        self.assertEqual(before, asdict(state))

    def test_encoder_cannot_predict_before_training_labels_mature(self) -> None:
        """Keep model fitting time distinct from historical feature cutoff."""
        # Arrange
        state = fit_target_encoding(self.frame, "category", 5, 50, "2025-12-02")
        future = self.frame.assign(as_of_time=pd.Timestamp("2025-11-25"))
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "not yet mature"):
            encode_target(future, state, False)

    def test_repeated_user_has_one_fold(self) -> None:
        """User grouping is stable across rows and process runs."""
        # Arrange / Act
        values = [user_fold("same_user", 5) for _ in range(4)]
        # Assert
        self.assertEqual(len(set(values)), 1)

    def test_sparse_unknown_is_separate_from_known(self) -> None:
        """Keep a new category in its own zero-training-support bucket."""
        # Arrange / Act
        matrix = sparse_categories(
            pd.DataFrame({"category": ["a", "future"]}), {"category": ["a"]}
        )
        # Assert
        np.testing.assert_array_equal(matrix.toarray(), [[0, 1], [1, 0]])


if __name__ == "__main__":
    unittest.main()
