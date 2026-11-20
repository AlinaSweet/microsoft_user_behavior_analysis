"""Reject chronological leakage before a stage 3.2 model can receive a matrix."""

import tempfile
import unittest
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.dao.traditional_repository import check_chronology
from user_behavior_analysis.dao.traditional_repository import read_temporal_split
from user_behavior_analysis.models.sampling_models import PartitionEvidence
from user_behavior_analysis.models.traditional_models import TemporalPlan
from user_behavior_analysis.service.wide_audit import file_record


class TraditionalBoundaryTests(unittest.TestCase):
    """Exercise the time-window and feature cutoff fail-closed controls."""

    def test_rejects_a_label_window_crossing_a_later_cutoff(self) -> None:
        """A training outcome must be fully known by the validation cutoff."""
        anchors = {
            "train": "2025-11-25",
            "validation": "2025-12-01",
            "test": "2025-12-09",
        }
        with self.assertRaisesRegex(ValueError, "overlaps"):
            check_chronology(anchors)

    def test_rejects_a_feature_event_at_the_prediction_cutoff(self) -> None:
        """The physical Parquet cutoff is checked before feature projection."""
        root = PROJECT_ROOT / ".cache/tests"
        root.mkdir(parents=True, exist_ok=True)
        cutoff = datetime.fromisoformat("2025-11-25")
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            path = Path(temporary) / "sample.parquet"
            pd.DataFrame(
                {
                    "as_of_time": [cutoff, cutoff],
                    "user_id": ["01", "02"],
                    "item_id": ["11", "12"],
                    "target": [0, 1],
                    "target_available": [True, True],
                    "label_start": [cutoff, cutoff],
                    "label_end_exclusive": [cutoff + timedelta(days=7)] * 2,
                    "pair_source_max_event_time": [cutoff - timedelta(hours=1), cutoff],
                    "feature": [0.2, 0.4],
                }
            ).to_parquet(path, index=False)
            record: PartitionEvidence = {
                "file": file_record(path),
                "rows": 2,
                "positives": 1,
                "negatives": 1,
                "positive_rate": 0.5,
                "row_share": 1.0,
                "pair_groups": 2,
                "positive_pair_groups": 1,
                "first_anchor": "2025-11-25",
                "last_anchor": "2025-11-25",
            }
            plan = TemporalPlan(
                {}, ("feature",), {"train": "2025-11-25"}, {"train": record}
            )
            with self.assertRaisesRegex(ValueError, "Invalid chronology"):
                read_temporal_split(plan, "train")


if __name__ == "__main__":
    unittest.main()
