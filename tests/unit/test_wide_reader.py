"""Check bounded catalog reads without access to the real business dataset."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.dao.wide_repository import iter_wide_features


class WideReaderTests(unittest.TestCase):
    """Use isolated on-disk Arrow fixtures and explicit catalog fingerprints."""

    def setUp(self) -> None:
        """Create a three-row approved snapshot and its linked audit report."""
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.root)
        mock = patch("user_behavior_analysis.common.utils.PROJECT_ROOT", self.root)
        mock.start()
        self.addCleanup(mock.stop)
        self.part = self.root / "part.parquet"
        pq.write_table(
            pa.table({"user_id": ["u1", "u2", "u3"], "value": [1, None, 3]}), self.part
        )
        self.snapshot = {
            "anchor": "2025-12-09",
            "rows": 3,
            "scalar_features": 1,
            "columns": ["user_id", "value"],
            "parts": [self._record(self.part)],
        }
        audit = self.root / "audit.json"
        audit.write_text(
            json.dumps({"status": "passed", "snapshots": [self.snapshot]}),
            encoding="utf-8",
        )
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(
            json.dumps(
                {
                    "status": "passed",
                    "kind": "prejoined_candidate_features",
                    "snapshots": [self.snapshot],
                    "audit_report": self._record(audit),
                }
            ),
            encoding="utf-8",
        )

    def _record(self, path: Path) -> dict[str, object]:
        """Fingerprint one fixture artifact.

        Args:
            path: Existing file in the isolated fixture root.

        Returns:
            The expected path, bytes and fingerprint.
        """
        return {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    def test_batches_preserve_requested_order_and_nulls(self) -> None:
        """Return small batches with unmodified missing values."""
        # Arrange / Act
        batches = list(
            iter_wide_features(self.catalog, "2025-12-09", ["value", "user_id"], 2)
        )
        # Assert
        self.assertEqual(
            ([batch.num_rows for batch in batches], batches[0].to_pydict()),
            ([2, 1], {"value": [1, None], "user_id": ["u1", "u2"]}),
        )

    def test_target_column_is_rejected(self) -> None:
        """Reject future outcomes absent from the approved feature schema."""
        # Arrange / Act / Assert
        with self.assertRaisesRegex(ValueError, "registered columns"):
            list(iter_wide_features(self.catalog, "2025-12-09", ["target"]))

    def test_modified_part_is_rejected_before_first_batch(self) -> None:
        """Fail closed when a data file changes after audit publication."""
        # Arrange
        pq.write_table(pa.table({"user_id": ["u1"], "value": [9]}), self.part)
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "artifact changed"):
            next(iter_wide_features(self.catalog, "2025-12-09", ["value"]))

    def test_unknown_cutoff_is_rejected(self) -> None:
        """Prevent accidental fallback to a different snapshot."""
        # Arrange / Act / Assert
        with self.assertRaisesRegex(ValueError, "Cutoff"):
            list(iter_wide_features(self.catalog, "2025-12-19", ["value"]))

    def test_invalid_batch_size_is_rejected(self) -> None:
        """Keep caller-controlled buffering within the declared resource bound."""
        # Arrange / Act / Assert
        with self.assertRaisesRegex(ValueError, "Batch size"):
            list(iter_wide_features(self.catalog, "2025-12-09", ["value"], 0))

    def test_catalog_cannot_substitute_another_row_count(self) -> None:
        """Compare the mutable catalog to the fingerprint-approved audit record."""
        # Arrange
        payload = json.loads(self.catalog.read_text(encoding="utf-8"))
        payload["snapshots"][0]["rows"] = 4
        self.catalog.write_text(json.dumps(payload), encoding="utf-8")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "differs from"):
            list(iter_wide_features(self.catalog, "2025-12-09", ["value"]))


if __name__ == "__main__":
    unittest.main()
