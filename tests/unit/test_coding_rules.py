"""Verify PDF-specific source audit findings with independent scenarios."""

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

from user_behavior_analysis.common.coding_rules import audit_source
from user_behavior_analysis.common.constants import PROJECT_ROOT


class CodingRuleTests(unittest.TestCase):
    """Exercise the standard checker against deliberately noncompliant fixtures."""

    def setUp(self) -> None:
        """Create one isolated source fixture."""
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self._resources = ExitStack()
        self.addCleanup(self._resources.close)
        directory = self._resources.enter_context(
            tempfile.TemporaryDirectory(dir=scratch)
        )
        self.path: Path = Path(directory) / "fixture.py"

    def tearDown(self) -> None:
        """Remove the temporary source fixture."""
        self._resources.close()

    def test_implicit_string_concatenation_is_rejected(self) -> None:
        """Verify that adjacent string tokens produce a finding."""
        # Arrange
        self.path.write_text('"""Fixture."""\nVALUE = "one" "two"\n')
        # Act
        issues = audit_source(self.path)
        # Assert
        self.assertTrue(any("Implicit" in issue.message for issue in issues))

    def test_untyped_public_api_is_rejected(self) -> None:
        """Verify that public API annotations are mandatory."""
        # Arrange
        self.path.write_text('"""Fixture."""\ndef fetch(value):\n    return value\n')
        # Act
        issues = audit_source(self.path)
        # Assert
        self.assertTrue(any("type annotations" in issue.message for issue in issues))

    def test_relative_import_is_rejected(self) -> None:
        """Verify that package-relative imports are forbidden."""
        # Arrange
        self.path.write_text('"""Fixture."""\nfrom . import helper\n')
        # Act
        issues = audit_source(self.path)
        # Assert
        self.assertTrue(any("absolute imports" in issue.message for issue in issues))
