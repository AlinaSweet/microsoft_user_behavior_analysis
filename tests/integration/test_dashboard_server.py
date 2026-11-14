"""Verify the real local EDA HTTP interface with an isolated project fixture."""

import json
import socket
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pandas as pd

from user_behavior_analysis.api.dashboard_server import create_dashboard_server
from user_behavior_analysis.common.constants import PROJECT_ROOT


class DashboardServerTests(unittest.TestCase):
    """Cover API validation, exported values and project-file confinement."""

    def setUp(self) -> None:
        """Start a loopback-only server using private two-row weighted events."""
        self.resources = ExitStack()
        self.addCleanup(self.resources.close)
        cache = PROJECT_ROOT / ".cache/tests"
        cache.mkdir(parents=True, exist_ok=True)
        directory = self.resources.enter_context(tempfile.TemporaryDirectory(dir=cache))
        source = Path(directory) / "source.parquet"
        frame = pd.DataFrame(
            [
                ("u", "a", "c", "2025-11-18 00", 1, 3),
                ("u", "b", "c", "2025-12-18 23", 4, 1),
            ],
            columns=[
                "user_id",
                "item_id",
                "category_id",
                "event_time",
                "behavior_type",
                "raw_count",
            ],
        )
        frame["event_time"] = pd.to_datetime(frame.event_time)
        frame.to_parquet(source, index=False)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        self.server = create_dashboard_server(port, source)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.resources.callback(self.server.server_close)
        self.resources.callback(self.worker.join, 5)
        self.resources.callback(self.server.shutdown)
        self.base = "http://127.0.0.1:" + str(port)

    def test_options_identify_actual_source(self) -> None:
        """Return actual bounds and a source fingerprint."""
        # Arrange / Act
        with urlopen(self.base + "/api/options", timeout=10) as response:
            payload = json.load(response)
        # Assert
        self.assertEqual(payload["categories"], ["c"])
        self.assertEqual(len(payload["source_sha256"]), 64)

    def test_export_preserves_weighted_records(self) -> None:
        """Export only weighted records inside the selected interval."""
        # Arrange / Act
        query = "/api/export?start=2025-11-18&end=2025-11-18&table=daily"
        with urlopen(self.base + query, timeout=10) as response:
            content = response.read().decode("utf-8-sig")
        # Assert
        self.assertIn("2025-11-18", content)
        self.assertIn(",3,", content)
        self.assertNotIn("2025-12-18", content)

    def test_duplicate_filter_is_rejected(self) -> None:
        """Reject ambiguous duplicate parameters before a query executes."""
        # Arrange / Act / Assert
        with self.assertRaises(HTTPError) as captured:
            with urlopen(self.base + "/api/data?start=a&start=b", timeout=10):
                self.fail("Expected an invalid-filter HTTP response")
        self.assertEqual(captured.exception.code, 400)

    def test_missing_dates_are_rejected(self) -> None:
        """Return a clear HTTP error when required interval dates are absent."""
        # Arrange / Act / Assert
        with self.assertRaises(HTTPError) as captured:
            with urlopen(self.base + "/api/data", timeout=10):
                self.fail("Expected a missing-filter HTTP response")
        self.assertEqual(captured.exception.code, 400)

    def test_project_files_are_not_served(self) -> None:
        """Serve only whitelisted app assets, never arbitrary repository files."""
        # Arrange / Act / Assert
        with self.assertRaises(HTTPError) as captured:
            with urlopen(self.base + "/README.md", timeout=10):
                self.fail("Expected an unavailable-file HTTP response")
        self.assertEqual(captured.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
