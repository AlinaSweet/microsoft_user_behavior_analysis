"""Provide streaming fingerprints and project-confined report persistence."""

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import datetime
from datetime import timezone
from pathlib import Path

from user_behavior_analysis.common.constants import HASH_CHUNK_BYTES
from user_behavior_analysis.common.constants import PROJECT_ROOT


def project_output_path(path: Path | str) -> Path:
    """Resolve an output path while preventing project-directory escape.

    Args:
        path: Absolute or project-relative output path.

    Returns:
        A validated absolute path under the project root.

    Raises:
        ValueError: The path or its symlink target escapes the project.
    """
    candidate = Path(path)
    candidate = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(PROJECT_ROOT):
        raise ValueError(f"Output must remain under {PROJECT_ROOT}: {path}")
    return resolved


def sha256_file(path: Path | str) -> str:
    """Fingerprint input contents without loading the complete file.

    Args:
        path: Existing input file, including an explicitly supplied external file.

    Returns:
        The hexadecimal SHA-256 content fingerprint.

    Raises:
        OSError: The file cannot be read.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path | str, payload: Mapping[str, object]) -> None:
    """Save a UTF-8 JSON report inside the project.

    Args:
        path: Project-confined output path.
        payload: Structured JSON-compatible report fields.

    Raises:
        ValueError: The output path escapes the project.
        OSError: The report cannot be written.

    Notes:
        Creates parent directories and replaces the designated report file.
    """
    output = project_output_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def utc_timestamp() -> str:
    """Return a timezone-explicit UTC timestamp for operation evidence.

    Returns:
        An ISO 8601 timestamp with the UTC offset.
    """
    return datetime.now(timezone.utc).isoformat()


def input_file_path(path: Path | str, root: Path = PROJECT_ROOT) -> Path:
    """Validate an input path while preserving intentional source symlinks.

    Args:
        path: Absolute input path or a path relative to root.
        root: Base directory for relative inputs.

    Returns:
        An existing input path; its contents are never rewritten.

    Raises:
        ValueError: A relative path lexically escapes its declared root.
        FileNotFoundError: The input file is unavailable.

    Notes:
        Source symlinks may intentionally point to user-provided external data.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(os.path.abspath(root / candidate))
        if not candidate.is_relative_to(root):
            raise ValueError("Relative source paths must remain in the project root")
    if not candidate.is_file():
        raise FileNotFoundError(f"Input file not found: {candidate}")
    return candidate
