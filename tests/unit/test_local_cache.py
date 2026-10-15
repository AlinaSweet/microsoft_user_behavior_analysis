"""Verify project-confined SQLite scratch configuration."""

import os
import unittest
from unittest.mock import patch

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.local_cache import configure_sqlite_cache


class LocalCacheTests(unittest.TestCase):
    """Exercise independent environment and path-safety scenarios."""

    def test_sqlite_cache_is_inside_project(self) -> None:
        """Create and select the fixed project cache directory."""
        # Arrange
        expected = PROJECT_ROOT / ".cache/sqlite"
        # Act
        actual = configure_sqlite_cache()
        # Assert
        self.assertEqual(actual, expected)
        self.assertTrue(actual.is_dir())
        self.assertEqual(os.environ["SQLITE_TMPDIR"], str(expected))

    def test_external_environment_value_is_replaced(self) -> None:
        """Prevent inherited environment values from redirecting scratch."""
        # Arrange
        with patch.dict(os.environ, {"SQLITE_TMPDIR": "/outside/project"}):
            # Act
            actual = configure_sqlite_cache()
            # Assert
            self.assertEqual(os.environ["SQLITE_TMPDIR"], str(actual))

    def test_escaping_symlink_is_rejected(self) -> None:
        """Propagate the output-path guard before changing environment state."""
        # Arrange
        target = "user_behavior_analysis.common.local_cache.project_output_path"
        with patch(target, side_effect=ValueError("outside project")):
            # Act / Assert
            with self.assertRaisesRegex(ValueError, "outside project"):
                configure_sqlite_cache()
