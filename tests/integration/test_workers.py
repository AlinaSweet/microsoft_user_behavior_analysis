"""Verify real Dask processes using synthetic data independent of private CSVs."""

import io
import json
import tempfile
import unittest
from contextlib import ExitStack
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from user_behavior_analysis.api.cli import main
from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.config import load_config
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.service.benchmark import benchmark_source
from user_behavior_analysis.service.environment import check_environment


class WorkerIntegrationTests(unittest.TestCase):
    """Exercise worker startup and measurements with isolated synthetic inputs."""

    def setUp(self) -> None:
        """Create synthetic CSV input and a bounded single-worker configuration."""
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        directory = self._resources.enter_context(
            tempfile.TemporaryDirectory(dir=scratch)
        )
        self.source: Path = Path(directory) / "source.csv"
        header = "time,user_id,item_id,item_category,behavior_type\n"
        records = (f"2025-12-06 02,{index:04d},002,004,1\n" for index in range(1200))
        self.source.write_text(header + "".join(records), encoding="utf-8")
        self.config: ProjectConfig = load_config()
        self.config["local_cluster"]["n_workers"] = 1
        self.config["local_cluster"]["memory_limit"] = "512MiB"
        self.config["local_cluster"]["csv_blocksize"] = "64KiB"
        self.config["benchmark"]["block_sizes"] = ["4KiB", "8KiB"]

    def tearDown(self) -> None:
        """Remove the isolated input after the worker processes have closed."""
        self._resources.close()

    def test_worker_configuration_is_applied(self) -> None:
        """Verify that a real worker receives the requested resource settings."""
        # Arrange
        expected_limit = 512 * 1024**2
        # Act
        report = check_environment(self.config, self.source)
        # Assert
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(report["actual_workers"]), 1)
        self.assertEqual(report["resource_plan"]["memory_limit_bytes"], expected_limit)

    def test_benchmark_returns_bounded_trials(self) -> None:
        """Verify sample measurements without overwriting production reports."""
        # Arrange
        self.config["local_cluster"]["csv_blocksize"] = "4KiB"
        expected_trials = 2
        # Act
        report = benchmark_source(self.config, self.source, rows=10, repeats=1)
        # Assert
        self.assertEqual(len(report["trials"]), expected_trials)
        self.assertTrue(
            all(trial["returned_sample_rows"] == 10 for trial in report["trials"])
        )
        self.assertEqual(report["worker_restart_count"], 0)

    def test_check_command_persists_isolated_report(self) -> None:
        """Verify the public command reads inputs and saves a scoped JSON report."""
        # Arrange
        configuration = self.source.parent / "runtime.yaml"
        configuration.write_text(yaml.safe_dump(self.config), encoding="utf-8")
        output = self.source.parent / "reports"
        arguments = [
            "--config",
            str(configuration),
            "check",
            "--data",
            str(self.source),
            "--output-dir",
            str(output),
        ]
        # Act
        with redirect_stdout(io.StringIO()):
            status = main(arguments)
        report = json.loads((output / "environment_check.json").read_text())
        # Assert
        self.assertEqual(status, 0)
        self.assertEqual(report["sample_rows"], 1000)
