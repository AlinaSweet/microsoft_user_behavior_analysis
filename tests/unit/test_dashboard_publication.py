"""Verify public dashboard publication works without private local datasets."""

import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.service.dashboard_publication import ASSETS
from user_behavior_analysis.service.dashboard_publication import MANIFEST
from user_behavior_analysis.service.dashboard_publication import build_site


class DashboardPublicationTests(unittest.TestCase):
    """Reject stale sources and export only explicit public dashboard assets."""

    def setUp(self) -> None:
        """Create an isolated aggregate-only repository with no raw data."""
        resources = ExitStack()
        self.addCleanup(resources.close)
        directory = resources.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        self.payload = {
            "filters": {"start": "2025-11-18", "end": "2025-11-18"},
            "overview": {"records": 3},
            "daily": [{"records": 3}],
            "behaviors": [{"records": 3}],
        }
        self.source = self.root / "view.json"
        self.source.write_text(json.dumps(self.payload), encoding="utf-8")
        self.manifest: dict[str, Any] = {
            "version": "fixture",
            "source_categories": 1,
            "source_sha256": "a" * 64,
            "views": [
                {
                    "label": "Fixture",
                    "path": "view.json",
                    "filters": self.payload["filters"],
                    "records": 3,
                    "sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
                }
            ],
        }
        (self.root / MANIFEST).parent.mkdir(parents=True)
        assets = self.root / ASSETS
        assets.mkdir(parents=True)
        for name in ("dashboard.html", "dashboard.js", "dashboard.css", "archive.js"):
            (assets / name).write_bytes((PROJECT_ROOT / ASSETS / name).read_bytes())
        self._save_manifest()

    def _save_manifest(self) -> None:
        """Persist fixture metadata after one deliberate corruption."""
        (self.root / MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_build_needs_no_private_data(self) -> None:
        """Build relative assets and saved aggregates without Parquet or SQLite."""
        # Arrange / Act
        public = build_site(self.root)
        html = (self.root / "_site/index.html").read_text(encoding="utf-8")
        # Assert
        self.assertEqual(len(public["views"]), 1)
        self.assertIn('src="./archive.js"', html)
        self.assertNotIn('href="/dashboard.css"', html)
        self.assertFalse((self.root / "_site/data/processed").exists())

    def test_stale_build_files_are_excluded(self) -> None:
        """Prevent a previous build artifact from leaking into the public site."""
        # Arrange
        target = self.root / "_site"
        target.mkdir()
        (target / "old.csv").write_text("stale", encoding="utf-8")
        # Act
        build_site(self.root)
        # Assert
        self.assertFalse((target / "old.csv").exists())

    def test_changed_source_is_rejected(self) -> None:
        """Refuse to publish a snapshot modified after its fingerprint was saved."""
        # Arrange
        self.source.write_text("{}", encoding="utf-8")
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            build_site(self.root)

    def test_external_source_is_rejected(self) -> None:
        """Do not export a manifest path outside the repository."""
        # Arrange
        self.manifest["views"][0]["path"] = "../private.json"
        self._save_manifest()
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "repository"):
            build_site(self.root)

    def test_filter_mismatch_is_rejected(self) -> None:
        """Prevent publishing one population under another view description."""
        # Arrange
        self.manifest["views"][0]["filters"] = {"start": "wrong"}
        self._save_manifest()
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "filters"):
            build_site(self.root)

    def test_unbalanced_counts_are_rejected(self) -> None:
        """Refuse totals that cannot reconcile with daily and behavioral records."""
        # Arrange
        self.manifest["views"][0]["records"] = 4
        self._save_manifest()
        # Act / Assert
        with self.assertRaisesRegex(ValueError, "reconcile"):
            build_site(self.root)


if __name__ == "__main__":
    unittest.main()
