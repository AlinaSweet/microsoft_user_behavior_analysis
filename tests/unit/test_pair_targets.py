"""Verify exact-pair labels, complete follow-up and strict three-key joins."""

import unittest

import duckdb
import pandas as pd

from user_behavior_analysis.service.pair_targets import audit_target_alignment
from user_behavior_analysis.service.pair_targets import create_pair_targets


class PairTargetTests(unittest.TestCase):
    """Exercise real SQL against repeated purchases and boundary events."""

    def setUp(self) -> None:
        """Create one user's two candidates and independent full event rows."""
        self.connection = duckdb.connect()
        self.addCleanup(self.connection.close)
        source = pd.DataFrame(
            [
                ("u1", "b", "2025-12-01 00", 4, 2),
                ("u2", "a", "2025-12-07 23", 4, 1),
                ("u1", "a", "2025-12-08 00", 4, 1),
            ],
            columns=["user_id", "item_id", "event_time", "behavior_type", "raw_count"],
        )
        source["event_time"] = pd.to_datetime(source["event_time"])
        self.connection.register("all_keys", source)
        self.connection.register(
            "raw_events",
            source.loc[source.index.repeat(source.raw_count)].drop(columns="raw_count"),
        )
        self.connection.execute(
            "CREATE TABLE wide AS SELECT '2025-12-01'::TIMESTAMP AS as_of_time,"
            + (
                "user_id,item_id FROM (VALUES ('u1','a'),('u1','b')"
                + ",('u2','a'))v(user_id,item_id)"
            )
        )

    def test_other_item_purchase_is_not_positive(self) -> None:
        """Do not copy a user's purchase of b onto candidate a."""
        # Arrange / Act
        create_pair_targets(self.connection, "2025-12-01")
        row = self.connection.execute(
            "SELECT target FROM targets WHERE user_id='u1' AND item_id='a'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (0,))

    def test_cutoff_purchase_is_included(self) -> None:
        """Include an exact-cutoff purchase in its own item label."""
        # Arrange / Act
        create_pair_targets(self.connection, "2025-12-01")
        row = self.connection.execute(
            (
                "SELECT target,future_buy_records FROM targets WHER"
                + "E user_id='u1' AND item_id='b'"
            )
        ).fetchone()
        # Assert
        self.assertEqual(row, (1, 2))

    def test_upper_boundary_is_excluded(self) -> None:
        """Exclude the purchase at the seventh day's exclusive endpoint."""
        # Arrange / Act
        create_pair_targets(self.connection, "2025-12-01")
        row = self.connection.execute(
            "SELECT future_buy_records FROM targets WHERE user_id='u1' AND item_id='a'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (0,))

    def test_last_observable_hour_is_included(self) -> None:
        """Keep a purchase one hour before the exclusive endpoint."""
        # Arrange / Act
        create_pair_targets(self.connection, "2025-12-01")
        row = self.connection.execute(
            "SELECT target FROM targets WHERE user_id='u2'"
        ).fetchone()
        # Assert
        self.assertEqual(row, (1,))

    def test_immature_labels_are_null(self) -> None:
        """Do not turn unobservable outcomes into negatives."""
        # Arrange
        self.connection.execute("UPDATE wide SET as_of_time='2025-12-08'")
        # Act
        result = create_pair_targets(self.connection, "2025-12-08")
        # Assert
        self.assertEqual(result["unavailable"], 3)

    def test_duplicate_candidate_is_rejected(self) -> None:
        """Fail on a duplicate instead of silently deduplicating it."""
        # Arrange
        self.connection.execute("INSERT INTO wide SELECT * FROM wide LIMIT 1")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "key/value"):
            create_pair_targets(self.connection, "2025-12-01")

    def test_missing_target_is_rejected(self) -> None:
        """Detect a lost target even when surviving values look valid."""
        # Arrange
        create_pair_targets(self.connection, "2025-12-01")
        self.connection.execute("DELETE FROM targets WHERE user_id='u2'")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "key/value"):
            audit_target_alignment(self.connection, "2025-12-01")

    def test_independent_raw_multiplicity_is_checked(self) -> None:
        """Reject source-key counts that differ from unaggregated events."""
        # Arrange
        self.connection.unregister("raw_events")
        self.connection.execute(
            (
                "CREATE VIEW raw_events AS SELECT user_id,item_id,e"
                + "vent_time,behavior_type FROM all_keys"
            )
        )
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Raw-event"):
            create_pair_targets(self.connection, "2025-12-01")


if __name__ == "__main__":
    unittest.main()
