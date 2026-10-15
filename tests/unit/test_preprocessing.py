"""Verify lossless encoding and registered-dataset input guards."""

import json
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.event_values import canonical_event_bytes
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.config import load_preprocessing_policy
from user_behavior_analysis.dao.dataset_repository import load_dataset_catalog
from user_behavior_analysis.models.preprocessing_models import EncodingPlan
from user_behavior_analysis.service.data_encoding import choose_encoding_plan
from user_behavior_analysis.service.data_encoding import encode_events


class PreprocessingTests(unittest.TestCase):
    """Exercise independent encoding or content-verification scenarios."""

    def setUp(self) -> None:
        """Create a project-local two-event source and its content catalog."""
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        self.root = Path(
            self._resources.enter_context(tempfile.TemporaryDirectory(dir=scratch))
        )
        self.frame = pd.DataFrame(
            {
                "event_id": [1, 2],
                "user_id": ["001", "002"],
                "item_id": ["01", "02"],
                "category_id": ["03", "04"],
                "behavior_type": ["1", "4"],
                "event_time": pd.to_datetime(["2025-11-18 00", "2025-11-19 01"]),
            }
        )
        self.dataset = self.root / "source"
        self.dataset.mkdir()
        self.part = self.dataset / "part_0.parquet"
        self.frame.to_parquet(self.part, index=False)
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(
            json.dumps(
                {
                    "dataset_path": str(self.dataset.relative_to(PROJECT_ROOT)),
                    "row_count": 2,
                    "parts": [
                        {
                            "path": str(self.part.relative_to(PROJECT_ROOT)),
                            "size_bytes": self.part.stat().st_size,
                            "sha256": sha256_file(self.part),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.plan = EncodingPlan(32, ("03", "04"), 2)

    def test_compact_encoding_preserves_canonical_values(self) -> None:
        """Preserve leading zeros and every event value through dtype changes."""
        # Arrange
        expected = canonical_event_bytes(self.frame)
        # Act
        table = encode_events(self.frame, self.plan)
        # Assert
        self.assertEqual(canonical_event_bytes(table.to_pandas()), expected)
        self.assertEqual(str(table.schema.field("behavior_type").type), "uint8")
        self.assertEqual(str(table.schema.field("event_id").type), "uint32")

    def test_uint32_lineage_overflow_is_rejected(self) -> None:
        """Reject truncation rather than wrapping a source record ordinal."""
        # Arrange
        self.frame.loc[0, "event_id"] = 2**32
        # Act / Assert
        with self.assertRaises(ValueError):
            encode_events(self.frame, self.plan)

    def test_unknown_dictionary_category_is_rejected(self) -> None:
        """Keep dictionary mismatches visible without manufacturing missing IDs."""
        # Arrange
        plan = EncodingPlan(32, ("03",), 2)
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "category"):
            encode_events(self.frame, plan)

    def test_invalid_behavior_cannot_be_encoded(self) -> None:
        """Reject invalid behavior values before unsigned conversion."""
        # Arrange
        self.frame.loc[0, "behavior_type"] = "9"
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "behavior"):
            encode_events(self.frame, self.plan)

    def test_timezone_is_not_silently_dropped(self) -> None:
        """Reject an unexpected timezone rather than altering time semantics."""
        # Arrange
        self.frame["event_time"] = pd.to_datetime(self.frame["event_time"], utc=True)
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "timezone"):
            encode_events(self.frame, self.plan)

    def test_changed_registered_part_is_rejected(self) -> None:
        """Compare contents with their registered fingerprint before processing."""
        # Arrange
        self.part.write_bytes(b"changed")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "differs"):
            load_dataset_catalog(self.catalog)

    def test_unregistered_part_is_rejected(self) -> None:
        """Prevent extra files from being silently included in a source dataset."""
        # Arrange
        (self.dataset / "extra.parquet").write_bytes(self.part.read_bytes())
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "inventory"):
            load_dataset_catalog(self.catalog)

    def test_dictionary_collection_has_a_bounded_fallback(self) -> None:
        """Use string storage when the configured category bound is exceeded."""
        # Arrange
        source = load_dataset_catalog(self.catalog)
        policy = replace(
            load_preprocessing_policy("configs/preprocessing.json"),
            dictionary_category_limit=1,
        )
        # Act
        plan = choose_encoding_plan(source, policy)
        # Assert
        self.assertIsNone(plan.categories)
