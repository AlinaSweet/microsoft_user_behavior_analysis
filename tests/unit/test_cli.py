"""Verify command output and expected failure logging without worker startup."""

import io
import json
import unittest
from contextlib import redirect_stdout

from user_behavior_analysis.api.cli import main


class CommandTests(unittest.TestCase):
    """Verify independent command-interface success and error scenarios."""

    def test_git_command_returns_json(self) -> None:
        """Verify the Git policy command returns machine-readable success."""
        # Arrange
        output = io.StringIO()
        # Act
        with redirect_stdout(output):
            status = main(["check-git"])
        # Assert
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["issues"], [])

    def test_missing_source_logs_actionable_error(self) -> None:
        """Verify missing input returns an error status and records the cause."""
        # Arrange
        arguments = ["check", "--data", ".cache/nonexistent_input_for_cli_test.csv"]
        # Act
        with self.assertLogs("user_behavior_analysis.api.cli", level="ERROR") as logs:
            status = main(arguments)
        # Assert
        self.assertEqual(status, 2)
        self.assertIn("Input file not found", logs.output[0])
