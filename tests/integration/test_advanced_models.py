"""Exercise real neural batches and leakage boundaries without the original CSV."""

import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from user_behavior_analysis.dao.sequence_repository import load_advanced_settings
from user_behavior_analysis.models.sequence_models import History
from user_behavior_analysis.models.sequence_models import SequenceSplit
from user_behavior_analysis.models.sequence_models import Vocabulary
from user_behavior_analysis.service.ensemble_diagnostics import split_meta_validation
from user_behavior_analysis.service.ensemble_explanations import din_shap
from user_behavior_analysis.service.ensemble_explanations import shapley_values
from user_behavior_analysis.service.sequence_networks import PurchaseNetwork
from user_behavior_analysis.service.sequence_training import Monitor
from user_behavior_analysis.service.sequence_training import fit_network
from user_behavior_analysis.service.sequence_training import probabilities


def _sample() -> SequenceSplit:
    """Create repeated users, simultaneous history tokens, and both outcome classes.

    Returns:
        A small in-memory stand-in for one audited cutoff.
    """
    rows = 64
    rng = np.random.default_rng(651)
    dense = rng.normal(size=(rows, 4)).astype(np.float32)
    tokens = torch.tensor([[2, 3, 2, 0]] * 8, dtype=torch.long)
    return SequenceSplit(
        torch.from_numpy(dense),
        torch.tensor([[2, 2], [3, 2]] * (rows // 2), dtype=torch.long),
        History(
            tokens,
            tokens,
            tokens,
            torch.from_numpy(rng.normal(size=(8, 4, 5)).astype(np.float32)),
            torch.tensor([[1, 1, 2, 0]] * 8, dtype=torch.long),
        ),
        torch.arange(rows) % 8,
        pd.DataFrame({"user_id": [f"user_{i % 8}" for i in range(rows)]}),
        (dense[:, 0] > 0.2).astype(np.int8),
    )


class AdvancedModelTests(unittest.TestCase):
    """Check real training and attribution on all required architecture types."""

    def setUp(self) -> None:
        """Use a mini training budget with deterministic model parameters."""
        self.settings = load_advanced_settings(Path("configs/stage3_advanced.json"))
        self.budget = self.settings.budget.copy()
        self.budget.update({"threads": 1, "max_epochs": 2, "batch_rows": 16})
        self.split = _sample()
        self.vocab: Vocabulary = {
            "items": ["i2", "i3"],
            "categories": ["c2", "c3"],
        }
        torch.set_num_threads(1)

    def test_recurrent_and_attention_models_train_on_cpu(self) -> None:
        """Require finite scores from trainable GRU, LSTM and multihead DIN."""
        # Arrange
        monitor = Monitor(self.split, np.arange(len(self.split.target)))
        variants = [
            item
            for item in self.settings.variants
            if item["name"] in {"gru_base", "lstm_base", "din_attention"}
        ]
        # Act / Assert
        for variant in variants:
            with self.subTest(variant=variant["name"]):
                run = fit_network(variant, self.vocab, self.split, self.budget, monitor)
                net = PurchaseNetwork(variant, self.vocab, 4)
                net.load_state_dict(run.state)
                scores = probabilities(net, self.split, 16, run.offset)
                self.assertEqual(scores.shape, self.split.target.shape)
                self.assertTrue(np.isfinite(scores).all())
                self.assertGreaterEqual(run.selected_epoch, 1)

    def test_train_only_checkpoint_has_no_validation_scores(self) -> None:
        """Keep the selected stacking base independent of the validation outcomes."""
        # Arrange
        self.budget["stack_epochs"] = 2
        variant = self.settings.variants[-1]
        # Act
        run = fit_network(variant, self.vocab, self.split, self.budget)
        # Assert
        self.assertEqual(run.selected_epoch, 2)
        self.assertTrue(all(row["monitor_auc"] is None for row in run.history))

    def test_din_grouped_shap_recovers_the_actual_margin(self) -> None:
        """Verify the complete grouped explanation against frozen neural outputs."""
        # Arrange
        net = PurchaseNetwork(self.settings.variants[-1], self.vocab, 4)
        labels = ("user_a", "pair_a", "item_a", "category_a")
        # Act
        names, values, error = din_shap(
            net,
            self.split.batch(slice(8)),
            self.split.batch(slice(8, 12)),
            labels,
        )
        # Assert
        self.assertEqual(values.shape, (8, len(names)))
        self.assertLess(error, 3e-5)

    def test_meta_user_groups_are_disjoint(self) -> None:
        """Keep every row belonging to one user on the same validation side."""
        # Arrange
        keys = self.split.keys
        # Act
        fit = split_meta_validation(keys, 90)
        # Assert
        self.assertFalse(set(keys.loc[fit, "user_id"]) & set(keys.loc[~fit, "user_id"]))
        self.assertEqual(keys.loc[fit, "user_id"].nunique(), 5)

    def test_exact_shapley_recovers_two_additive_features(self) -> None:
        """Recover the known signed contributions of a simple two-feature game."""
        # Arrange
        coalitions = np.array([[0.0, 2.0, -1.0, 1.0]])
        # Act
        values = shapley_values(coalitions)
        # Assert
        np.testing.assert_array_equal(values, [[2, -1]])


if __name__ == "__main__":
    unittest.main()
