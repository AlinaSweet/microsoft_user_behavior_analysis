"""Keep first-stage SQLite sorting and grouping scratch inside the project."""

import os
from pathlib import Path

from user_behavior_analysis.common.utils import project_output_path


def configure_sqlite_cache() -> Path:
    """Configure a validated project directory before native SQLite startup.

    Returns:
        The project-local directory used for disk-backed temporary sorting.

    Raises:
        ValueError: A symlink redirects the cache outside the project.
        OSError: The cache directory cannot be created.

    Notes:
        Updates the process environment inherited by child processes. Shell
        entry points also set the variable before starting the interpreter.
    """
    directory = project_output_path(".cache/sqlite")
    directory.mkdir(parents=True, exist_ok=True)
    os.environ["SQLITE_TMPDIR"] = str(directory)
    return directory
