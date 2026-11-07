"""Exercise independent prejoined-feature failure conditions on small relations."""

import unittest

import duckdb

from user_behavior_analysis.service.wide_contracts import MANAGEMENT
from user_behavior_analysis.service.wide_contracts import compare_candidate_keys
from user_behavior_analysis.service.wide_contracts import compare_source
from user_behavior_analysis.service.wide_contracts import identifier
from user_behavior_analysis.service.wide_contracts import relation_contract
from user_behavior_analysis.service.wide_profiles import profile_wide


class WideContractTests(unittest.TestCase):
    """Check one grain, join or missing-value contract in each scenario."""

    def setUp(self) -> None:
        """Create a fresh in-memory relation with legal historical values."""
        self.connection = duckdb.connect()
        self.addCleanup(self.connection.close)
        self.connection.execute(
            "CREATE TABLE source_user AS SELECT 'u1' AS user_id,"
            + "TIMESTAMP '2025-12-09' AS as_of_time,"
            + "TIMESTAMP '2025-12-08' AS source_max_event_time,"
            + "NULL::DOUBLE AS user_buy_recency_hours"
        )
        self.connection.execute(
            "CREATE TABLE wide AS SELECT *, 'i1' AS item_id, 'c1' AS category_id "
            + "FROM source_user"
        )

    def test_matched_source_null_is_preserved(self) -> None:
        """Accept a legitimate source null and compare it with null-safe equality."""
        # Arrange / Act
        result = compare_source(self.connection, "user", ["user_buy_recency_hours"])
        # Assert
        self.assertEqual(result["differences"]["user_buy_recency_hours"], 0)

    def test_duplicate_source_key_is_rejected(self) -> None:
        """Detect a dimension key that would multiply candidates."""
        # Arrange
        self.connection.execute("INSERT INTO source_user SELECT * FROM source_user")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Invalid keys/time"):
            relation_contract(
                self.connection, "source_user", ["as_of_time", "user_id"], "2025-12-09"
            )

    def test_null_key_is_rejected(self) -> None:
        """Stop publication when a join identity is missing."""
        # Arrange
        self.connection.execute("UPDATE wide SET user_id=NULL")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Invalid keys/time"):
            relation_contract(
                self.connection, "wide", ["as_of_time", "user_id"], "2025-12-09"
            )

    def test_wrong_cutoff_is_rejected(self) -> None:
        """Reject accidentally mixing a future snapshot into the current relation."""
        # Arrange / Act / Assert
        with self.assertRaisesRegex(ValueError, "Invalid keys/time"):
            relation_contract(
                self.connection, "wide", ["as_of_time", "user_id"], "2025-12-02"
            )

    def test_event_at_cutoff_is_rejected(self) -> None:
        """Keep the historical upper boundary exclusive."""
        # Arrange
        self.connection.execute("UPDATE wide SET source_max_event_time=as_of_time")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Invalid keys/time"):
            relation_contract(
                self.connection, "wide", ["as_of_time", "user_id"], "2025-12-09"
            )

    def test_unmatched_user_is_rejected(self) -> None:
        """Retain evidence of an unmatched candidate through the left join."""
        # Arrange
        self.connection.execute("UPDATE wide SET user_id='missing'")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Unmatched source"):
            compare_source(self.connection, "user", ["user_buy_recency_hours"])

    def test_changed_feature_value_is_rejected(self) -> None:
        """Detect imputation that silently changes a source-defined null to zero."""
        # Arrange
        self.connection.execute("UPDATE wide SET user_buy_recency_hours=0")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Feature value mismatch"):
            compare_source(self.connection, "user", ["user_buy_recency_hours"])

    def test_distinct_items_for_same_user_are_valid(self) -> None:
        """Keep multiple historical candidate items for one user."""
        # Arrange
        self.connection.execute(
            "INSERT INTO wide SELECT * REPLACE('i2' AS item_id) FROM wide"
        )
        # Act
        result = relation_contract(
            self.connection, "wide", ["as_of_time", "user_id", "item_id"], "2025-12-09"
        )
        # Assert
        self.assertEqual(result["rows"], 2)

    def test_equal_row_totals_do_not_hide_changed_keys(self) -> None:
        """Detect a lost candidate despite unchanged overall row count."""
        # Arrange
        self.connection.execute(
            "ALTER TABLE wide RENAME source_max_event_time "
            + "TO pair_source_max_event_time"
        )
        self.connection.execute(
            "ALTER TABLE wide ADD COLUMN history_coverage_30d INTEGER DEFAULT 21"
        )
        self.connection.execute(
            "ALTER TABLE wide ADD COLUMN history_complete_30d BOOLEAN DEFAULT FALSE"
        )
        columns = [
            (
                field
                if field != "pair_source_max_event_time"
                else field + " AS source_max_event_time"
            )
            for field in MANAGEMENT
        ]
        self.connection.execute(
            "CREATE TABLE source_pair AS SELECT " + ",".join(columns) + " FROM wide"
        )
        self.connection.execute("UPDATE wide SET item_id='lost'")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Candidate keys"):
            compare_candidate_keys(self.connection)

    def test_unsafe_identifier_is_rejected(self) -> None:
        """Prevent arbitrary SQL fragments from entering registry expressions."""
        # Arrange / Act / Assert
        with self.assertRaisesRegex(ValueError, "Unsafe name"):
            identifier("field; DROP TABLE wide")

    def test_profile_identifies_matched_source_missing(self) -> None:
        """Keep semantic missing separate from failed entity joins."""
        # Arrange
        definition = {
            "name": "user_buy_recency_hours",
            "table": "user",
            "family": "生命周期",
            "dtype": "float64",
            "missing_policy": "无观测购买保留缺失",
        }
        # Act
        result = profile_wide(self.connection, [definition])[0]
        # Assert
        self.assertEqual(
            (result["missing_rate"], result["unmatched_source_rows"]), (1.0, 0)
        )


if __name__ == "__main__":
    unittest.main()
