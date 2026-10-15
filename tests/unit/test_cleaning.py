"""Verify validation and global-key behavior with isolated source records."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.config import load_cleaning_policy
from user_behavior_analysis.dao.cleaning_repository import CLEAN_EVENTS
from user_behavior_analysis.dao.cleaning_repository import export_query
from user_behavior_analysis.dao.cleaning_repository import ingest_partition
from user_behavior_analysis.dao.cleaning_repository import open_cleaning_database
from user_behavior_analysis.dao.cleaning_repository import row_accounting
from user_behavior_analysis.dao.source_repository import source_declaration_status
from user_behavior_analysis.models.cleaning_models import PartitionRequest
from user_behavior_analysis.service.anomaly_audit import summarize_activity_histogram
from user_behavior_analysis.service.cleaning_integrity import verify_export
from user_behavior_analysis.service.data_quality import detect_activity_anomalies
from user_behavior_analysis.service.validation import SOURCE_COLUMNS
from user_behavior_analysis.service.validation import normalize_partition


class CleaningTests(unittest.TestCase):
    """Exercise one independent validation or persistence scenario per test."""

    def setUp(self) -> None:
        """Create project-local fixtures for one scenario."""
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        self.root = Path(
            self._resources.enter_context(tempfile.TemporaryDirectory(dir=scratch))
        )
        self.policy = load_cleaning_policy("configs/cleaning.json")

    def _partition(
        self, rows: list[list[str]], partition_id: int = 0, first_record: int = 1
    ) -> Path:
        frame = pd.DataFrame(rows, columns=SOURCE_COLUMNS).astype("string[pyarrow]")
        request = PartitionRequest(self.root, partition_id, first_record, self.policy)
        evidence = normalize_partition(frame, request)
        return Path(evidence["valid_path"])

    def test_identifier_leading_zeros_survive(self) -> None:
        """Preserve identifier characters through normalization."""
        # Arrange
        rows = [["2025-12-01 00", "001", "0002", "03", "1"]]
        # Act
        path = self._partition(rows)
        # Assert
        self.assertEqual(pd.read_parquet(path).iloc[0]["user_id"], "001")

    def test_literal_na_is_not_rewritten(self) -> None:
        """Treat a literal identifier NA as a string rather than a missing code."""
        # Arrange
        rows = [["2025-12-01 00", "NA", "0002", "03", "1"]]
        # Act
        path = self._partition(rows)
        # Assert
        self.assertEqual(pd.read_parquet(path).iloc[0]["user_id"], "NA")

    def test_impossible_calendar_date_is_rejected(self) -> None:
        """Reject a formatted timestamp that is not a real calendar date."""
        # Arrange
        rows = [["2025-02-30 00", "001", "002", "03", "1"]]
        # Act
        path = self._partition(rows)
        rejected = pd.read_parquet(self.root / "rejected/part_00000.parquet")
        # Assert
        self.assertEqual(len(pd.read_parquet(path)), 0)
        self.assertIn("invalid_time", rejected.iloc[0]["failure_reasons"])

    def test_unknown_behavior_is_rejected(self) -> None:
        """Quarantine behavior codes outside the four task-defined values."""
        # Arrange
        rows = [["2025-12-01 00", "001", "002", "03", "9"]]
        # Act
        self._partition(rows)
        rejected = pd.read_parquet(self.root / "rejected/part_00000.parquet")
        # Assert
        self.assertIn("invalid_behavior_type", rejected.iloc[0]["failure_reasons"])

    def test_future_policy_boundary_is_exclusive(self) -> None:
        """Reject a timestamp equal to the explicit upper time boundary."""
        # Arrange
        rows = [[self.policy.maximum_event_time, "001", "002", "03", "1"]]
        # Act
        self._partition(rows)
        rejected = pd.read_parquet(self.root / "rejected/part_00000.parquet")
        # Assert
        self.assertIn("time_outside_policy", rejected.iloc[0]["failure_reasons"])

    def test_empty_identifier_is_rejected(self) -> None:
        """Quarantine empty identifiers without inventing replacement users."""
        # Arrange
        rows = [["2025-12-01 00", "", "002", "03", "1"]]
        # Act
        self._partition(rows)
        rejected = pd.read_parquet(self.root / "rejected/part_00000.parquet")
        # Assert
        self.assertIn("missing_user_id", rejected.iloc[0]["failure_reasons"])

    def test_duplicate_across_partitions_is_removed_globally(self) -> None:
        """Deduplicate records that cannot meet in a single parsing chunk."""
        # Arrange
        rows = [["2025-12-01 00", "001", "002", "03", "1"]]
        first = self._partition(rows)
        second = self._partition(rows, partition_id=1, first_record=2)
        # Act
        with open_cleaning_database(self.root / "global.sqlite") as connection:
            ingest_partition(connection, first)
            ingest_partition(connection, second)
            result = row_accounting(connection, 2, 0)
        # Assert
        self.assertEqual(result["clean_rows"], 1)
        self.assertEqual(result["duplicate_rows_removed"], 1)
        self.assertTrue(result["reconciled"])

    def test_conflicting_duplicate_key_is_quarantined_as_a_whole(self) -> None:
        """Avoid silently choosing a category for conflicting duplicate keys."""
        # Arrange
        rows = [
            ["2025-12-01 00", "001", "002", "03", "1"],
            ["2025-12-01 00", "001", "002", "04", "1"],
        ]
        path = self._partition(rows)
        # Act
        with open_cleaning_database(self.root / "global.sqlite") as connection:
            ingest_partition(connection, path)
            result = row_accounting(connection, 2, 0)
        # Assert
        self.assertEqual(result["clean_rows"], 0)
        self.assertEqual(result["conflicting_rows_quarantined"], 2)
        self.assertTrue(result["reconciled"])

    def test_export_verification_detects_changed_values(self) -> None:
        """Detect altered output even when row counts stay the same."""
        # Arrange
        path = self._partition([["2025-12-01 00", "001", "002", "03", "1"]])
        with open_cleaning_database(self.root / "global.sqlite") as connection:
            ingest_partition(connection, path)
            paths = export_query(connection, CLEAN_EVENTS, self.root / "events", 2)
            frame = pd.read_parquet(paths[0])
            frame.loc[0, "user_id"] = "tampered"
            frame.to_parquet(paths[0], index=False)
            # Act
            result = verify_export(connection, paths, 2)
        # Assert
        self.assertFalse(result["values_match"])

    def test_iqr_flags_activity_without_deleting_events(self) -> None:
        """Flag a long activity tail while retaining the canonical events."""
        # Arrange
        rows = [
            ["2025-12-01 00", str(user), str(item), "03", "1"]
            for user, count in enumerate([1, 1, 1, 1, 1, 100])
            for item in range(count)
        ]
        path = self._partition(rows)
        with open_cleaning_database(self.root / "global.sqlite") as connection:
            ingest_partition(connection, path)
            # Act
            metrics = detect_activity_anomalies(connection, self.root / "flags", 20)
            remaining = row_accounting(connection, 105, 0)
        # Assert
        self.assertEqual(metrics[0]["iqr_upper"], 1.0)
        self.assertEqual(metrics[0]["iqr_flagged_entities"], 1)
        self.assertEqual(remaining["clean_rows"], 105)

    def test_histogram_quartile_uses_linear_interpolation(self) -> None:
        """Interpolate the quartile between adjacent ordered count values."""
        # Arrange
        histogram = {1: 1, 3: 1}
        # Act
        summary = summarize_activity_histogram(histogram)
        # Assert
        self.assertEqual(summary["q1"], 1.5)
        self.assertEqual(summary["q3"], 2.5)

    def test_histogram_flags_a_long_activity_tail(self) -> None:
        """Count IQR flags from frequencies without expanding entity rows."""
        # Arrange
        histogram = {1: 5, 100: 1}
        # Act
        summary = summarize_activity_histogram(histogram)
        # Assert
        self.assertEqual(summary["entities"], 6)
        self.assertEqual(summary["iqr_flagged_entities"], 1)

    def test_empty_histogram_is_rejected(self) -> None:
        """Keep an absent distribution visible rather than inventing thresholds."""
        # Arrange
        histogram: dict[int, int] = {}
        # Act / Assert
        with self.assertRaises(ValueError):
            summarize_activity_histogram(histogram)

    def test_matching_source_declaration_is_recognized(self) -> None:
        """Associate a use declaration with its exact input fingerprint."""
        # Arrange
        metadata = self.root / "data/catalog/data_provenance.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(
            json.dumps(
                {"source_sha256": "a" * 64, "local_processing_authorized": True}
            ),
            encoding="utf-8",
        )
        # Act
        with patch(
            "user_behavior_analysis.dao.source_repository.PROJECT_ROOT", self.root
        ):
            status = source_declaration_status("a" * 64)
        # Assert
        self.assertIn("authorizes local processing", status)

    def test_declaration_does_not_cover_a_different_fingerprint(self) -> None:
        """Avoid attributing a recorded declaration to different input bytes."""
        # Arrange
        metadata = self.root / "data/catalog/data_provenance.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(
            json.dumps(
                {"source_sha256": "a" * 64, "local_processing_authorized": True}
            ),
            encoding="utf-8",
        )
        # Act
        with patch(
            "user_behavior_analysis.dao.source_repository.PROJECT_ROOT", self.root
        ):
            status = source_declaration_status("b" * 64)
        # Assert
        self.assertEqual(status, "No matching source declaration recorded")
