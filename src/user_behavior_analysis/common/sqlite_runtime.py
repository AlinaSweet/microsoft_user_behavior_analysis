"""Confine SQLite temporary sort and aggregation files to the project cache."""

import os
from pathlib import Path

from user_behavior_analysis.common.utils import project_output_path


def configure_sqlite_temporary_storage() -> Path:
    """Set the process-local Unix SQLite temporary directory before connecting.

    Returns:
        Validated writable cache directory under this project.

    Notes:
        Creates the directory and sets SQLITE_TMPDIR for this Python process and
        its children. No system-wide environment or deprecated PRAGMA is changed.
    """
    directory = project_output_path(".cache/sqlite")
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["SQLITE_TMPDIR"] = str(directory)
    return directory
