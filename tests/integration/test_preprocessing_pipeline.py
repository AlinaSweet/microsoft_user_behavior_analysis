"""Verify compact events and complete dimension aggregates through the CLI."""

import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from user_behavior_analysis.api.cli import main
from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.config import load_config
from user_behavior_analysis.service.aggregate_audit import audit_aggregate_values


class PreprocessingPipelineTests(unittest.TestCase):
    """Exercise source, compact events, aggregate relations, and read comparisons."""

    def test_preprocess_command_conserves_all_three_dimensions(self) -> None:
        """Verify the public workflow with groups spanning multiple input files."""
        # Arrange
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with ExitStack() as resources:
            root = Path(
                resources.enter_context(tempfile.TemporaryDirectory(dir=scratch))
            )
            source = root / "source"
            source.mkdir()
            frame = pd.DataFrame(
                {
                    "event_id": [1, 2, 3, 4, 5],
                    "user_id": ["001", "001", "001", "002", "002"],
                    "item_id": ["01", "01", "02", "01", "01"],
                    "category_id": ["03", "03", "04", "03", "03"],
                    "behavior_type": ["1", "3", "4", "2", "4"],
                    "event_time": pd.to_datetime(
                        [
                            "2025-11-18 00",
                            "2025-11-18 00",
                            "2025-11-18 01",
                            "2025-11-19 05",
                            "2025-11-19 06",
                        ]
                    ),
                }
            )
            parts = []
            for index, subset in enumerate((frame.iloc[:2], frame.iloc[2:])):
                path = source / f"part_{index}.parquet"
                subset.to_parquet(path, index=False)
                parts.append(
                    {
                        "path": str(path.relative_to(PROJECT_ROOT)),
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "dataset_path": str(source.relative_to(PROJECT_ROOT)),
                        "row_count": 5,
                        "parts": parts,
                    }
                ),
                encoding="utf-8",
            )
            policy = root / "policy.json"
            settings = json.loads(
                (PROJECT_ROOT / "configs/preprocessing.json").read_text(
                    encoding="utf-8"
                )
            )
            settings.update(
                {"batch_rows": 2, "row_group_rows": 2, "benchmark_repeats": 1}
            )
            policy.write_text(json.dumps(settings), encoding="utf-8")
            output = root / "processed"
            arguments = [
                "preprocess",
                "--catalog",
                str(catalog),
                "--policy",
                str(policy),
                "--output-dir",
                str(output),
                "--report-dir",
                str(root / "reports"),
            ]
            # Act
            with redirect_stdout(io.StringIO()):
                status = main(arguments)
            report = json.loads(
                (root / "reports/preprocessing.json").read_text(encoding="utf-8")
            )
            users = pd.read_parquet(output / "aggregates/user_daily_stats")
            items = pd.read_parquet(output / "aggregates/item_daily_stats")
            times = pd.read_parquet(output / "aggregates/time_hourly_stats")
            configuration = load_config()
            configuration["local_cluster"]["n_workers"] = 1
            configuration["local_cluster"]["memory_limit"] = "512MiB"
            aggregate_audits = audit_aggregate_values(
                configuration, output / "events", output / "aggregates"
            )
            # Assert
            self.assertEqual(status, 0)
            self.assertTrue(
                all(item["status"] == "passed" for item in aggregate_audits)
            )
            self.assertTrue(report["values_match"])
            self.assertEqual(
                dict(zip(users["user_id"], users["event_count"])),
                {
                    "001": 3,
                    "002": 2,
                },
            )
            self.assertEqual(len(items), 3)
            self.assertEqual(len(times), 4)
            self.assertEqual(int(items["event_count"].sum()), 5)
            self.assertEqual(int(times["buy_count"].sum()), 2)
            self.assertEqual({trial["rows"] for trial in report["read_trials"]}, {5})
            self.assertEqual(len(report["read_trials"]), 3)
