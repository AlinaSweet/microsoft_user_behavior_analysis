"""Build a dependency-free GitHub Pages artifact from verified saved aggregates."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

MANIFEST = "outputs/reports/dashboard_publication_20261117/manifest.json"
ASSETS = "src/user_behavior_analysis/assets/eda"


def _contained(root: Path, relative: str) -> Path:
    """Resolve a repository-relative source without traversing outside the tree.

    Args:
        root: Resolved repository or isolated test root.
        relative: Manifest-owned relative file name.

    Returns:
        Verified contained source path.

    Raises:
        ValueError: A source is absolute or escapes the repository.
    """
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError("Public source must stay within the repository")
    return path


def build_site(root: Path) -> dict[str, Any]:
    """Publish only allowlisted assets and hash-checked aggregate snapshots.

    Args:
        root: Project root; generated files are confined to its _site directory.

    Returns:
        Public view manifest used by the browser.

    Raises:
        ValueError: A snapshot changed, is oversized or disagrees with its filters.
        FileNotFoundError: Required published assets or snapshots are unavailable.
    """
    root = root.resolve()
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    verified = []
    for view in manifest["views"]:
        raw = _contained(root, view["path"]).read_bytes()
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("Split large public aggregates before publication")
        if hashlib.sha256(raw).hexdigest() != view["sha256"]:
            raise ValueError("Published snapshot fingerprint changed")
        payload = json.loads(raw)
        if payload["filters"] != view["filters"]:
            raise ValueError("Published filters differ from snapshot metadata")
        records = payload["overview"]["records"]
        if (
            any(
                sum(row["records"] for row in payload[key]) != records
                for key in ("daily", "behaviors")
            )
            or records != view["records"]
        ):
            raise ValueError("Published aggregates do not reconcile")
        verified.append((view, payload))
    target = root / "_site"
    if target.is_symlink() or (target / "data").is_symlink():
        raise ValueError("Public build directories must not be symbolic links")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(exist_ok=True)
    (target / "data").mkdir(exist_ok=True)
    for filename in ("dashboard.css", "dashboard.js", "archive.js"):
        (target / filename).write_bytes((root / ASSETS / filename).read_bytes())
    html = (root / ASSETS / "dashboard.html").read_text(encoding="utf-8")
    html = html.replace('href="/dashboard.css"', 'href="./dashboard.css"')
    html = html.replace(
        '<script src="/dashboard.js"></script>',
        '<script src="./archive.js"></script><script src="./dashboard.js"></script>',
    )
    (target / "index.html").write_text(html, encoding="utf-8")
    public_views = []
    for index, (view, payload) in enumerate(verified):
        filename = "data/view_" + str(index).zfill(2) + ".json"
        (target / filename).write_text(
            json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ),
            encoding="utf-8",
        )
        public_views.append(
            {"label": view["label"], "path": filename, "filters": view["filters"]}
        )
    public = {
        "version": manifest["version"],
        "views": public_views,
        "source_sha256": manifest["source_sha256"],
        "source_categories": manifest["source_categories"],
    }
    (target / "manifest.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (target / ".nojekyll").touch()
    return public
