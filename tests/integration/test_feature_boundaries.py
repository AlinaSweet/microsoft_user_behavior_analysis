"""Verify historical features, future labels and sequence boundaries together."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.feature_business import create_history_hours
from user_behavior_analysis.service.feature_business import lifecycle_features
from user_behavior_analysis.service.feature_funnels import funnel_features
from user_behavior_analysis.service.feature_latent_transform import (
    encode_sequence_tensors,
)
from user_behavior_analysis.service.feature_quality import export_user_targets
from user_behavior_analysis.service.feature_quality import temporal_count_controls
from user_behavior_analysis.service.feature_sequences import export_sequence_inputs
from user_behavior_analysis.service.feature_sequences import sequence_statistics
from user_behavior_analysis.service.feature_snapshots import build_statistical_tables
from user_behavior_analysis.service.feature_snapshots import create_history_view

ANCHOR = "2025-12-01"


def _source_frame() -> pd.DataFrame:
    """Create repeated keys, hour ties and exact historical/future boundaries.

    Returns:
        Small canonical key-frequency table with deliberately unequal counts.
    """
    rows = [
        ("u1", "i1", "c1", "2025-11-23 23", 1, 2),
        ("u1", "i1", "c1", "2025-11-24 00", 1, 3),
        ("u1", "i1", "c1", "2025-11-30 08", 1, 90),
        ("u1", "i1", "c1", "2025-11-30 08", 3, 1),
        ("u1", "i1", "c1", "2025-11-30 09", 3, 2),
        ("u1", "i1", "c1", "2025-11-30 10", 2, 1),
        ("u1", "i1", "c1", "2025-11-30 11", 4, 1),
        ("u1", "i2", "c2", "2025-11-30 12", 1, 1),
        ("u1", "i3", "c2", "2025-11-30 12", 1, 2),
        ("u2", "i4", "c3", "2025-11-29 12", 1, 1),
        ("u2", "i4", "c3", "2025-11-29 12", 3, 1),
        ("u2", "i4", "c3", "2025-11-30 12", 4, 1),
        ("u3", "i5", "c3", "2025-11-20 00", 1, 1),
        ("u1", "i1", "c1", "2025-12-01 00", 4, 7),
        ("u2", "i4", "c3", "2025-12-07 23", 4, 1),
        ("u3", "i5", "c3", "2025-12-08 00", 4, 1),
        ("u2", "i4", "c3", "2025-12-08 23", 1, 1),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "user_id",
            "item_id",
            "category_id",
            "event_time",
            "behavior_type",
            "raw_count",
        ],
    )
    frame["event_time"] = pd.to_datetime(frame["event_time"])
    return frame


class FeatureBoundaryTests(unittest.TestCase):
    """Exercise actual SQL builders on an isolated complete-record fixture."""

    def setUp(self) -> None:
        """Create private base keys and a fresh historical snapshot for each case."""
        directory = PROJECT_ROOT / ".cache/tests"
        directory.mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        root = Path(
            self._resources.enter_context(tempfile.TemporaryDirectory(dir=directory))
        )
        options = json.loads((PROJECT_ROOT / "configs/feature_system.json").read_text())
        for key in (
            "source_catalog",
            "source_database",
            "base_dir",
            "output_dir",
            "report_dir",
            "eda_report_dir",
        ):
            options.pop(key)
        options["sequence_length"] = 3
        self.settings = FeatureSettings(
            source_catalog=root / "catalog.json",
            source_database=root / "source.sqlite",
            base_dir=root / "base",
            output_dir=root / "features",
            report_dir=root / "reports",
            eda_report_dir=root / "eda",
            options=options,
        )
        key_path = self.settings.base_dir / "key_hour/data.parquet"
        key_path.parent.mkdir(parents=True)
        _source_frame().to_parquet(key_path, index=False)
        self.connection = self._resources.enter_context(duckdb.connect())
        self.history = create_history_view(self.connection, self.settings, ANCHOR)
        self.definitions = build_statistical_tables(
            self.connection, self.settings, ANCHOR, self.history
        )

    def test_raw_multiplicity_is_preserved(self) -> None:
        """Include the lower boundary and retain all same-key record weight."""
        # Arrange / Act
        row = self.connection.execute(
            "SELECT user_event_count_7d,user_key_count_7d FROM user_stats "
            + "WHERE user_id='u1'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (101, 8))

    def test_anchor_events_are_excluded_from_features(self) -> None:
        """Keep a purchase exactly at the cutoff outside historical inputs."""
        # Arrange / Act
        row = self.connection.execute(
            "SELECT user_buy_count_7d FROM user_stats WHERE user_id='u1'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (1,))

    def test_zero_denominator_stays_missing(self) -> None:
        """Distinguish an inactive user's undefined ratio from a measured zero."""
        # Arrange / Act
        row = self.connection.execute(
            "SELECT user_event_count_7d,user_purchase_record_share_7d "
            + "FROM user_stats WHERE user_id='u3'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (0, None))

    def test_hour_threshold_only_marks(self) -> None:
        """Flag 91 raw records while retaining their statistical count."""
        # Arrange
        create_history_hours(self.connection)
        # Act
        lifecycle_features(self.connection, self.history["parameters"])
        row = self.connection.execute(
            "SELECT user_flagged_hour_count_7d,user_max_hour_record_count_7d "
            + "FROM user_lifecycle WHERE user_id='u1'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (1, 91))

    def test_same_hour_is_not_a_confirmed_funnel_transition(self) -> None:
        """Leave the ordered cart stage unconfirmed when its hour equals pv."""
        # Arrange / Act
        funnel_features(self.connection, self.history["parameters"])
        row = self.connection.execute(
            "SELECT pair_funnel_has_pv_7d,pair_funnel_has_cart_7d "
            + "FROM pair_funnel WHERE user_id='u2'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (1, 0))

    def test_completed_cross_hour_funnel_is_counted(self) -> None:
        """Recognize the fixture's observed pv-cart-fav-buy path."""
        # Arrange / Act
        funnel_features(self.connection, self.history["parameters"])
        row = self.connection.execute(
            "SELECT pair_funnel_has_buy_7d FROM pair_funnel "
            + "WHERE user_id='u1' AND item_id='i1'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (1,))

    def test_censored_last_hour_is_not_a_transition(self) -> None:
        """Count only observed neighboring hour pairs inside the gap limit."""
        # Arrange
        create_history_hours(self.connection)
        # Act
        sequence_statistics(self.connection, self.history["parameters"], 24)
        row = self.connection.execute(
            "SELECT user_seq_observed_transition_pairs_7d "
            + "FROM user_sequence WHERE user_id='u2'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (1,))

    def test_tied_hour_truncation_is_explicit(self) -> None:
        """Mark a retained boundary that cuts two simultaneous item units."""
        # Arrange
        settings = replace(
            self.settings, options=dict(self.settings.options, sequence_length=1)
        )
        # Act
        export_sequence_inputs(
            self.connection, settings, ANCHOR, self.history["parameters"]
        )
        row = self.connection.execute(
            "SELECT boundary_hour_truncated FROM sequence_inputs WHERE user_id='u1'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (True,))

    def test_unknown_and_padding_tokens_are_distinct(self) -> None:
        """Encode observed new items as UNK and absent positions as PAD."""
        # Arrange
        export_sequence_inputs(
            self.connection, self.settings, ANCHOR, self.history["parameters"]
        )
        latent = self.settings.output_dir / "latent"
        latent.mkdir()
        pd.DataFrame({"item_id": ["i1"]}).to_parquet(
            latent / "item_vocabulary.parquet", index=False
        )
        pd.DataFrame({"category_id": ["c1"]}).to_parquet(
            latent / "category_vocabulary.parquet", index=False
        )
        # Act
        encode_sequence_tensors(self.settings, ANCHOR, pd.Series(["u1", "u2", "u3"]))
        path = self.settings.output_dir / "snapshots" / ANCHOR / "sequence_tensors.npz"
        with np.load(path, allow_pickle=False) as arrays:
            tokens = np.array(arrays["item_tokens"], copy=True)
            valid = np.array(arrays["valid_mask"], copy=True)
        # Assert
        self.assertTrue(bool(np.all(tokens[~valid] == 0)))
        self.assertTrue(bool(np.all(tokens[valid] >= 1)))
        self.assertEqual(tokens[2].tolist(), [1, 0, 0])

    def test_future_label_upper_boundary_is_exclusive(self) -> None:
        """Exclude a purchase at t+7d and include purchases at t and t+7d-1h."""
        # Arrange / Act
        export_user_targets(
            self.connection, self.settings, ANCHOR, self.history["parameters"]
        )
        rows = self.connection.execute(
            "SELECT user_id,target FROM user_targets ORDER BY user_id"
        ).fetchall()
        # Assert
        self.assertEqual(rows, [("u1", 1), ("u2", 1), ("u3", 0)])

    def test_unavailable_future_labels_remain_null(self) -> None:
        """Keep the latest unavailable future window different from negatives."""
        # Arrange
        parameters = dict(self.history["parameters"], anchor=pd.Timestamp("2025-12-09"))
        # Act
        export_user_targets(self.connection, self.settings, "2025-12-09", parameters)
        rows = self.connection.execute(
            "SELECT target,target_available FROM user_targets"
        ).fetchall()
        # Assert
        self.assertEqual(rows, [(None, False)] * 3)

    def test_all_entity_grains_conserve_counts(self) -> None:
        """Reconcile raw multiplicity and distinct keys at all five grains."""
        # Arrange / Act
        result = temporal_count_controls(self.connection, self.history["parameters"])
        # Assert
        self.assertTrue(all(row["counts_match"] for row in result["entity_controls"]))

    def test_input_path_escape_is_rejected(self) -> None:
        """Reject a feature configuration path outside the project boundary."""
        # Arrange / Act / Assert
        with self.assertRaises(ValueError):
            load_feature_settings(Path("../outside.json"))


if __name__ == "__main__":
    unittest.main()
