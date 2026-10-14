"""Persist artifact manifests and inspect Git tracking policy."""

import json
import re
import subprocess
from pathlib import Path
from typing import cast

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.constants import SMALL_FILE_LIMIT_BYTES
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.models.report_models import ArtifactManifest
from user_behavior_analysis.models.report_models import ArtifactRequest
from user_behavior_analysis.models.report_models import GitFilesReport
from user_behavior_analysis.models.report_models import VerificationReport


def register_artifact(
    request: ArtifactRequest, root: Path = PROJECT_ROOT
) -> tuple[Path, ArtifactManifest]:
    """Register content identity and provenance without copying data.

    Args:
        request: Validated artifact details grouped in one immutable request.
        root: Project-confined catalog root, optionally isolated for tests.

    Returns:
        Saved JSON manifest path and the structured artifact metadata.

    Raises:
        ValueError: A name, kind, recipe, or output path is invalid.
        FileNotFoundError: The input artifact does not exist.

    Notes:
        Creates or replaces the named catalog manifest under root.
    """
    path, name, kind = request.path, request.name, request.kind
    recipe, share_location = request.recipe, request.share_location
    root = project_output_path(root)
    if kind not in {"raw", "interim", "processed"}:
        raise ValueError(f"Invalid artifact kind: {kind}")
    if not recipe.strip():
        raise ValueError("Artifact origin or recipe must not be empty")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(
            "Manifest name must use snake_case starting with a lowercase letter"
        )
    path = input_file_path(path, root)
    logical = path.absolute()
    displayed = (
        str(logical.relative_to(root)) if logical.is_relative_to(root) else path.name
    )
    payload: ArtifactManifest = {
        "name": name,
        "kind": kind,
        "project_path": displayed,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "created_at_utc": utc_timestamp(),
        "reproduction_or_origin": recipe,
        "share_location": share_location,
        "distribution_status": "location_recorded" if share_location else "local_only",
        "data_file_in_git": (
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", str(logical)],
                cwd=root,
                capture_output=True,
                check=False,
            ).returncode
            == 0
        ),
    }
    output = root / "data/catalog" / f"{name}.json"
    write_json(output, payload)
    return output, payload


def check_git_files(root: Path = PROJECT_ROOT) -> GitFilesReport:
    """Check tracked and staged files against the artifact policy.

    Args:
        root: Project-confined Git working directory.

    Returns:
        File count, size limit, and explicit policy issues.

    Raises:
        subprocess.CalledProcessError: Git cannot enumerate the tracked files.
    """
    root = project_output_path(root)
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    names = [part.decode("utf-8") for part in result.stdout.split(b"\0") if part]
    issues = []
    for name in names:
        path = root / name
        if not path.exists():
            issues.append(f"Tracked file is missing: {name}")
            continue
        if path.is_symlink():
            issues.append(f"Local symbolic link must not be tracked: {name}")
        if path.stat().st_size > SMALL_FILE_LIMIT_BYTES:
            issues.append(f"Tracked file exceeds 10 MiB: {name}")
        if (
            any(
                name.startswith(prefix)
                for prefix in ("data/raw/", "data/interim/", "data/processed/")
            )
            and path.name != ".gitkeep"
        ):
            issues.append(f"Large data directory must not be tracked: {name}")
    return {
        "tracked_file_count": len(names),
        "small_file_limit_bytes": SMALL_FILE_LIMIT_BYTES,
        "issues": issues,
    }


def verify_artifact(
    manifest_path: Path | str, data_path: Path | str
) -> VerificationReport:
    """Verify file content against a catalog fingerprint.

    Args:
        manifest_path: Project-confined metadata manifest.
        data_path: Source file, including explicitly supplied external inputs.

    Returns:
        Successful verification and its content fingerprint.

    Raises:
        ValueError: Manifest fields are invalid or the data differs.
        OSError: A source or manifest cannot be read.
    """
    manifest = project_output_path(manifest_path)
    loaded: object = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Manifest must be a mapping")
    expected = cast(ArtifactManifest, loaded)
    source = input_file_path(data_path)
    if not isinstance(expected.get("size_bytes"), int):
        raise ValueError("Manifest size must be an integer")
    fingerprint = expected.get("sha256")
    if not isinstance(fingerprint, str) or not re.fullmatch(
        "[0-9a-f]{64}", fingerprint
    ):
        raise ValueError("Manifest SHA-256 must be hexadecimal")
    matches = source.stat().st_size == expected["size_bytes"]
    if not matches or sha256_file(source) != fingerprint:
        raise ValueError("File differs from its manifest")
    return {"status": "passed", "sha256": fingerprint}
