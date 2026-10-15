"""Verify the public clean command using independent synthetic CSV records."""

import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd
import yaml

from user_behavior_analysis.api.cli import main
from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.config import load_config


class CleaningPipelineTests(unittest.TestCase):
    """Exercise bounded workers, global keys, and persisted public evidence."""

    def setUp(self) -> None:
        """Create a tiny source whose duplicate key spans parsing partitions."""
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        self.root = Path(
            self._resources.enter_context(tempfile.TemporaryDirectory(dir=scratch))
        )
        self.source = self.root / "source.csv"
        self.source.write_text(
            "time,user_id,item_id,item_category,behavior_type\n"
            + "2025-12-01 00,001,002,03,1\n"
            + "2025-12-02 00,002,002,03,4\n"
            + "2025-12-01 00,001,002,03,1\n"
            + "2025-02-30 00,003,002,03,1\n"
            + "2025-12-03 00,003,005,06,1\n"
            + "2025-12-03 00,003,005,07,1\n"
            + "2025-12-03 00,003,005,07,9\n"
            + "2025-12-04 00,004,0005,08,2\n"
        )
        config = load_config()
        config["local_cluster"]["n_workers"] = 1
        config["local_cluster"]["memory_limit"] = "512MiB"
        self.configuration = self.root / "runtime.yaml"
        self.configuration.write_text(yaml.safe_dump(config))
        policy = json.loads((PROJECT_ROOT / "configs/cleaning.json").read_text())
        policy["chunk_rows"] = 2
        policy["export_rows"] = 2
        self.policy = self.root / "policy.json"
        self.policy.write_text(json.dumps(policy))

    def test_clean_command_reconciles_cross_partition_records(self) -> None:
        """Verify exact reconciliation and full output comparison end to end."""
        # Arrange
        reports = self.root / "reports"
        output = io.StringIO()
        arguments = [
            "--config",
            str(self.configuration),
            "clean",
            "--data",
            str(self.source),
            "--policy",
            str(self.policy),
            "--output-dir",
            str(self.root / "clean"),
            "--report-dir",
            str(reports),
        ]
        # Act
        with redirect_stdout(output):
            status = main(arguments)
        report = json.loads((reports / "quality.json").read_text())
        events = pd.read_parquet(self.root / "clean/events")
        # Assert
        self.assertEqual(status, 0)
        self.assertEqual(
            report["row_accounting"],
            {
                "input_rows": 8,
                "invalid_rows": 2,
                "valid_before_deduplication": 6,
                "duplicate_rows_removed": 1,
                "conflicting_rows_quarantined": 2,
                "conflicting_keys": 1,
                "clean_rows": 3,
                "reconciled": True,
            },
        )
        self.assertTrue(report["output_integrity"]["values_match"])
        self.assertIn("001", events["user_id"].tolist())
        self.assertEqual(report["source_sha256_before"], report["source_sha256_after"])
