"""Confine SQLite temporary sort and aggregation files to the project cache."""

import os
from pathlib import Path

from user_behavior_analysis.common.utils import project_output_path


def configure_sqlite_temporary_storage() -> Path:
    """Validate the project cache and set the native SQLite environment.

    Returns:
        Validated writable cache directory under this project.

    Notes:
        Creates the directory and sets SQLITE_TMPDIR for this Python process and
        its children. Shell entrypoints set it before Python starts because the
        macOS runtime can cache its value during native-engine initialization.
        Existing notebook processes should be launched with this setting. No
        system-wide environment or deprecated PRAGMA is changed.
    """
    directory = project_output_path(".cache/sqlite")
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["SQLITE_TMPDIR"] = str(directory)
    return directory
