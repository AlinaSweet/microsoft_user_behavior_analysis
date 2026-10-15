"""Verify normalized import safety and read-only query contracts."""

import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from contextlib import closing
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.dao.database_repository import create_database
from user_behavior_analysis.dao.database_repository import import_event_batch
from user_behavior_analysis.dao.sqlite_client import SQLiteClient
from user_behavior_analysis.dao.sqlite_client import query_path


def _event() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": [1],
            "user_id": ["001"],
            "item_id": ["01"],
            "category_id": ["03"],
            "behavior_type": [1],
            "event_time": pd.to_datetime(["2025-11-01 00:00:00"]),
        }
    )


class DatabaseTests(unittest.TestCase):
    """Cover one import or query safety scenario per test."""

    def setUp(self) -> None:
        """Create an isolated normalized project-local database."""
        directory = PROJECT_ROOT / ".cache/tests"
        directory.mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        temporary = self._resources.enter_context(
            tempfile.TemporaryDirectory(dir=directory)
        )
        self.path = Path(temporary) / "events.sqlite"
        self.connection = self._resources.enter_context(
            closing(create_database(self.path))
        )

    def test_identifier_leading_zeros_survive(self) -> None:
        """Keep source string identifiers in normalized relations."""
        # Arrange
        frame = _event()
        # Act
        import_event_batch(self.connection, frame)
        result = self.connection.execute(
            "SELECT user_id, item_id FROM behaviors"
        ).fetchone()
        # Assert
        self.assertEqual(result, ("001", "01"))

    def test_global_duplicate_is_rejected(self) -> None:
        """Enforce the business key across separate imports."""
        # Arrange
        import_event_batch(self.connection, _event())
        duplicate = _event()
        duplicate["event_id"] = 99
        # Act / Assert
        with self.assertRaises(sqlite3.IntegrityError):
            import_event_batch(self.connection, duplicate)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM behaviors").fetchone()[0], 1
        )

    def test_cross_batch_category_conflict_rolls_back(self) -> None:
        """Preserve the original item category after a conflicting batch."""
        # Arrange
        import_event_batch(self.connection, _event())
        changed = _event()
        changed["event_id"] = 2
        changed["category_id"] = "different"
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "conflicting categories"):
            import_event_batch(self.connection, changed)
        self.assertEqual(
            self.connection.execute("SELECT category_id FROM items").fetchone()[0], "03"
        )

    def test_fractional_event_id_is_not_truncated(self) -> None:
        """Reject an unsafe integer conversion before insertion."""
        # Arrange
        frame = _event()
        frame["event_id"] = [1.5]
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "integer event_id"):
            import_event_batch(self.connection, frame)

    def test_timezone_is_not_silently_removed(self) -> None:
        """Reject aware times when the canonical source is naive."""
        # Arrange
        frame = _event()
        frame["event_time"] = frame["event_time"].dt.tz_localize("Asia/Shanghai")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "naive"):
            import_event_batch(self.connection, frame)

    def test_foreign_keys_are_enabled(self) -> None:
        """Reject an event with missing user, item and time parents."""
        # Arrange
        statement = "INSERT INTO behaviors VALUES (?, ?, ?, ?, ?)"
        # Act / Assert
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                statement, (1, "missing", "missing", 1, "2025-11-01 00:00:00")
            )

    def test_query_parameter_is_literal(self) -> None:
        """Treat SQL-looking parameter text as an identifier value."""
        # Arrange
        import_event_batch(self.connection, _event())
        client = SQLiteClient(self.path)
        # Act
        result = client.query_frame(
            "SELECT user_id FROM users WHERE user_id = :user",
            {"user": "001' OR 1=1 --"},
        )
        # Assert
        self.assertTrue(result.empty)

    def test_read_interface_rejects_mutation(self) -> None:
        """Keep the database read-only even if a caller supplies write SQL."""
        # Arrange
        import_event_batch(self.connection, _event())
        client = SQLiteClient(self.path)
        # Act / Assert
        with self.assertRaises(pd.errors.DatabaseError):
            client.query_frame("DELETE FROM behaviors")

    def test_small_frame_limit_requires_streaming(self) -> None:
        """Reject results exceeding the declared DataFrame budget."""
        # Arrange
        client = SQLiteClient(self.path)
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "iter_frames"):
            client.query_frame("SELECT behavior_type FROM behavior_types", max_rows=2)

    def test_unregistered_query_path_is_rejected(self) -> None:
        """Prevent path traversal through a query name."""
        # Arrange
        name = "../schema"
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "Unregistered"):
            query_path(name)

    def test_input_column_order_does_not_change_meaning(self) -> None:
        """Project named fields before parameterized tuple insertion."""
        # Arrange
        frame = _event()
        frame = frame[frame.columns[::-1]]
        # Act
        import_event_batch(self.connection, frame)
        result = self.connection.execute(
            "SELECT user_id, item_id, category_id FROM canonical_events"
        ).fetchone()
        # Assert
        self.assertEqual(result, ("001", "01", "03"))

    def test_funnel_excludes_exact_window_end(self) -> None:
        """Keep a cart exactly seven days after its view outside the window."""
        # Arrange
        frame = pd.concat([_event()] * 4, ignore_index=True)
        frame["event_id"] = [1, 2, 3, 4]
        frame["behavior_type"] = [1, 3, 2, 4]
        frame["event_time"] = pd.to_datetime(
            [
                "2025-11-01 00",
                "2025-11-08 00",
                "2025-11-08 01",
                "2025-11-08 02",
            ]
        )
        import_event_batch(self.connection, frame)
        # Act
        result = (
            SQLiteClient(self.path)
            .query_frame(
                query_path("strict_funnel").read_text(encoding="utf-8"),
                {
                    "start_time": "2025-11-01 00:00:00",
                    "end_time": "2025-12-01 00:00:00",
                    "window_days": 7,
                },
            )
            .iloc[0]
        )
        # Assert
        self.assertEqual(result["eligible_view_pairs"], 1)
        self.assertEqual(result["cart_pairs"], 0)

    def test_behavior_table_avoids_transitive_attributes(self) -> None:
        """Keep item category and derived calendar fields out of the fact table."""
        # Arrange
        query = "PRAGMA table_info(behaviors)"
        # Act
        names = {row[1] for row in self.connection.execute(query)}
        # Assert
        self.assertEqual(
            names, {"event_id", "user_id", "item_id", "behavior_type", "event_time"}
        )
