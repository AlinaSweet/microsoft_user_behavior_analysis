"""Fit real CPU classifiers on a deterministic miniature temporal design."""

import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.dao.traditional_repository import load_traditional_settings
from user_behavior_analysis.models.traditional_models import MODEL_FAMILIES
from user_behavior_analysis.models.traditional_models import LabeledMatrix
from user_behavior_analysis.service.traditional_tuning import predict_probability
from user_behavior_analysis.service.traditional_tuning import tune_family


class TraditionalModelSmokeTests(unittest.TestCase):
    """Exercise all native libraries and seeded trials during ordinary CI."""

    def test_three_families_complete_optuna_and_keep_their_baseline(self) -> None:
        """Each study produces a fitted baseline and valid validation winner."""
        settings = replace(
            load_traditional_settings(Path("configs/stage3_traditional.json")),
            trials_per_model=4,
            threads=1,
        )
        values = np.random.default_rng(24).normal(size=(720, 5)).astype(np.float32)
        outcomes = (values[:, 0] + values[:, 1] > 0.7).astype(np.int8)
        train = LabeledMatrix(values[:520], outcomes[:520])
        validation = LabeledMatrix(values[520:], outcomes[520:])
        with threadpool_limits(limits=1):
            for family in MODEL_FAMILIES:
                with self.subTest(family=family):
                    result = tune_family(family, train, validation, settings)
                    scores = predict_probability(
                        result.tuned.estimator, validation.values
                    )
                    self.assertEqual(result.baseline.trial, 0)
                    self.assertEqual(len(result.trials), 4)
                    self.assertGreaterEqual(
                        result.tuned.validation_auc, result.baseline.validation_auc
                    )
                    self.assertEqual(scores.shape, validation.target.shape)
                    self.assertTrue(np.isfinite(scores).all())


if __name__ == "__main__":
    unittest.main()
