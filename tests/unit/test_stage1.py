"""Verify independent source, memory, and artifact-policy scenarios."""

import copy
import json
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

import yaml

from user_behavior_analysis.artifacts import SMALL_FILE_LIMIT
from user_behavior_analysis.artifacts import check_git_files
from user_behavior_analysis.artifacts import register
from user_behavior_analysis.artifacts import sha256_file
from user_behavior_analysis.artifacts import verify_artifact
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.models.report_models import ArtifactRequest
from user_behavior_analysis.runtime import ROOT
from user_behavior_analysis.runtime import load_config
from user_behavior_analysis.runtime import read_sample
from user_behavior_analysis.runtime import resolve_source
from user_behavior_analysis.runtime import resource_plan


class _ProjectFixture(unittest.TestCase):
    """Create project-local inputs isolated from the original dataset."""

    def setUp(self) -> None:
        """Create isolated synthetic inputs for one scenario."""
        # Arrange
        (ROOT / ".cache/tests").mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        directory = self._resources.enter_context(
            tempfile.TemporaryDirectory(dir=ROOT / ".cache/tests")
        )
        self.root: Path = Path(directory)
        self.csv: Path = self.root / "sample.csv"
        self.csv.write_text(
            "time,user_id,item_id,item_category,behavior_type\n"
            + "2025-12-06 02,001,0002,004,1\n",
            encoding="utf-8",
        )
        self.config: ProjectConfig = load_config()

    def tearDown(self) -> None:
        """Remove temporary test data after the scenario."""
        self._resources.close()


class SourceTests(_ProjectFixture):
    """Verify source selection and unchanged identifier representation."""

    def test_environment_path_beats_default(self) -> None:
        """Verify environment path beats default."""
        # Arrange
        self.config["data"]["default_path"] = "missing.csv"
        # Act / Assert
        self.assertEqual(
            resolve_source(self.config, env={"USER_BEHAVIOR_CSV": str(self.csv)}),
            self.csv,
        )

    def test_explicit_path_beats_environment(self) -> None:
        """Verify explicit path beats environment."""
        # Arrange
        # Act / Assert
        self.assertEqual(
            resolve_source(
                self.config, str(self.csv), {"USER_BEHAVIOR_CSV": "missing.csv"}
            ),
            self.csv,
        )

    def test_bad_csv_header_is_rejected(self) -> None:
        """Verify bad csv header is rejected."""
        # Arrange
        self.csv.write_text("user_id,item_id\n1,2\n")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "columns differ"):
            resolve_source(self.config, str(self.csv))

    def test_id_leading_zeros_survive(self) -> None:
        """Verify id leading zeros survive."""
        # Arrange
        rows = 1
        # Act
        frame = read_sample(
            str(self.csv), rows, "utf-8", self.config["data"]["columns"]
        )
        # Assert
        self.assertEqual(frame.loc[0, "user_id"], "001")
        # Assert
        self.assertEqual(frame.loc[0, "item_id"], "0002")

    def test_relative_source_path_cannot_escape_project(self) -> None:
        """Verify relative source path cannot escape project."""
        # Arrange
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "remain in the project"):
            resolve_source(self.config, "../user_behavior.csv")

    def test_source_symlink_can_point_to_user_input(self) -> None:
        """Verify an intentional input symlink remains usable."""
        # Arrange
        link = self.root / "source_link.csv"
        link.symlink_to(self.csv)
        # Act
        source = input_file_path(link.relative_to(ROOT))
        # Assert
        self.assertEqual(source.read_bytes(), self.csv.read_bytes())

    def test_output_path_cannot_escape_project(self) -> None:
        """Verify a parent traversal cannot designate an output file."""
        # Arrange
        target = "../outside.json"
        # Act / Assert
        with self.assertRaises(ValueError):
            project_output_path(target)

    def test_output_symlink_cannot_escape_project(self) -> None:
        """Verify a resolved external symlink cannot receive output."""
        # Arrange
        link = self.root / "external_output"
        link.symlink_to(ROOT.parent, target_is_directory=True)
        # Act / Assert
        with self.assertRaises(ValueError):
            project_output_path(link / "report.json")


class ResourceConfigurationTests(_ProjectFixture):
    """Verify independent resource and configuration validation scenarios."""

    def test_resource_plan_stays_within_available_budget(self) -> None:
        """Verify resource plan stays within available budget."""
        # Arrange
        available = 1200 * 1024**2
        # Act
        plan = resource_plan(self.config, available=available, cpu_count=2)
        # Assert
        self.assertEqual(plan["n_workers"], 1)
        self.assertLessEqual(
            plan["total_worker_budget_bytes"], int(1200 * 1024**2 * 0.70)
        )
        self.assertGreaterEqual(plan["memory_limit_bytes"], 512 * 1024**2)

    def test_insufficient_memory_is_rejected(self) -> None:
        """Verify insufficient memory is rejected."""
        # Arrange
        # Act / Assert
        with self.assertRaisesRegex(RuntimeError, "memory is too low"):
            resource_plan(self.config, available=100 * 1024**2, cpu_count=1)

    def test_unordered_thresholds_are_rejected(self) -> None:
        """Verify unordered thresholds are rejected."""
        # Arrange
        config = copy.deepcopy(self.config)
        config["distributed"]["worker"]["memory"]["pause"] = 0.60
        path = self.root / "bad.yaml"
        path.write_text(yaml.safe_dump(config))
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            load_config(path)

    def test_malformed_configuration_structure_is_rejected(self) -> None:
        """Verify a nested scalar produces an actionable configuration error."""
        # Arrange
        path = self.root / "bad.yaml"
        path.write_text("distributed: wrong_structure\n")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "must be a mapping"):
            load_config(path)

    def test_boolean_worker_count_is_rejected(self) -> None:
        """Verify booleans cannot masquerade as integer worker counts."""
        # Arrange
        document = yaml.safe_load((ROOT / "configs/dask.yaml").read_text())
        document["local_cluster"]["n_workers"] = True
        path = self.root / "bad.yaml"
        path.write_text(yaml.safe_dump(document))
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "positive integer"):
            load_config(path)

    def test_invalid_yaml_preserves_exception_context(self) -> None:
        """Verify invalid YAML raises a project error with its parser cause."""
        # Arrange
        path = self.root / "bad.yaml"
        path.write_text("data: [unterminated\n")
        # Act / Assert
        with self.assertRaises(ValueError) as caught:
            load_config(path)
        self.assertIsInstance(caught.exception.__cause__, yaml.YAMLError)


class ArtifactTests(_ProjectFixture):
    """Verify catalog persistence and content-integrity scenarios."""

    def test_manifest_records_source_fingerprint(self) -> None:
        """Verify catalog metadata identifies unchanged input contents."""
        # Arrange
        request = ArtifactRequest(self.csv, "sample", "raw", "test source")
        # Act
        output, payload = register(request, root=self.root)
        # Assert
        self.assertEqual(
            json.loads(output.read_text())["sha256"], sha256_file(self.csv)
        )
        self.assertEqual(payload["distribution_status"], "local_only")

    def test_verification_accepts_matching_contents(self) -> None:
        """Verify unchanged input passes its catalog check."""
        # Arrange
        output, _ = register(
            ArtifactRequest(self.csv, "sample", "raw", "test source"), root=self.root
        )
        # Act
        result = verify_artifact(output, self.csv)
        # Assert
        self.assertEqual(result["status"], "passed")

    def test_verification_rejects_changed_contents(self) -> None:
        """Verify changed input fails its catalog check."""
        # Arrange
        output, _ = register(
            ArtifactRequest(self.csv, "sample", "raw", "test source"), root=self.root
        )
        self.csv.write_text("different data\n")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "differs"):
            verify_artifact(output, self.csv)

    def test_manifest_name_cannot_escape_catalog(self) -> None:
        """Verify manifest name cannot escape catalog."""
        # Arrange
        # Act / Assert
        with self.assertRaises(ValueError):
            register(
                ArtifactRequest(self.csv, "../outside", "raw", "test"), root=self.root
            )

    def test_manifest_records_actual_git_tracking_status(self) -> None:
        """Verify manifest records actual git tracking status."""
        # Arrange
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "add", "sample.csv"], cwd=self.root, check=True)
        _, payload = register(
            ArtifactRequest(self.csv, "tracked_sample", "interim", "test input"),
            root=self.root,
        )
        # Act / Assert
        self.assertTrue(payload["data_file_in_git"])


class GitPolicyTests(_ProjectFixture):
    """Verify one Git tracking rule in each isolated scenario."""

    def _tracked_fixture(self, name: str) -> str:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text((ROOT / ".gitignore").read_text())
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("example")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        return subprocess.check_output(["git", "ls-files"], cwd=self.root, text=True)

    def test_git_policy_rejects_large_files(self) -> None:
        """Verify a tracked file above the size limit produces an issue."""
        # Arrange
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        large = self.root / "large.bin"
        with large.open("wb") as handle:
            handle.truncate(SMALL_FILE_LIMIT + 1)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        # Act
        issues = check_git_files(self.root)["issues"]
        # Assert
        self.assertTrue(any("exceeds 10 MiB" in issue for issue in issues))

    def test_git_policy_rejects_raw_data(self) -> None:
        """Verify a small raw-data file is still excluded from Git delivery."""
        # Arrange
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        raw = self.root / "data/raw/source.csv"
        raw.parent.mkdir(parents=True)
        raw.write_text("raw\n")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        # Act
        issues = check_git_files(self.root)["issues"]
        # Assert
        self.assertTrue(any("Large data directory" in issue for issue in issues))

    def test_small_csv_is_trackable(self) -> None:
        """Verify a small report is included in the staged file list."""
        # Arrange
        name = "outputs/reports/summary.csv"
        # Act
        tracked = self._tracked_fixture(name)
        # Assert
        self.assertIn(name, tracked)

    def test_large_data_directory_is_ignored(self) -> None:
        """Verify intermediate data stays out of the staged file list."""
        # Arrange
        name = "data/interim/large.csv"
        # Act
        tracked = self._tracked_fixture(name)
        # Assert
        self.assertNotIn(name, tracked)

    def test_virtual_environment_is_ignored(self) -> None:
        """Verify reproducibility environments stay out of Git."""
        # Arrange
        name = ".venv-repro/cache"
        # Act
        tracked = self._tracked_fixture(name)
        # Assert
        self.assertNotIn(name, tracked)


if __name__ == "__main__":
    unittest.main()
