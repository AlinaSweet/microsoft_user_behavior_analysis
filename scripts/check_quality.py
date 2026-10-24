"""Run required tools and cache successful checks by source content."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from importlib import metadata
from pathlib import Path

from user_behavior_analysis.common.coding_rules import audit_source
from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.artifact_repository import check_git_files

SOURCE_DIRECTORIES = ("src", "tests", "scripts")
QUALITY_TOOLS = ("black", "isort", "flake8", "mypy", "pylint")


def _sources() -> list[Path]:
    """Collect the Python files covered by the project quality checks.

    Returns:
        Sorted source paths from src, tests, and scripts.
    """
    return sorted(
        path
        for directory in SOURCE_DIRECTORIES
        for path in (PROJECT_ROOT / directory).rglob("*.py")
    )


def _fingerprint(sources: list[Path]) -> str:
    """Hash source, policy, and tool versions for quality-cache reuse.

    Args:
        sources: Ordered Python source files included in the quality check.

    Returns:
        A SHA-256 digest covering file paths, contents, and checker versions.

    Raises:
        OSError: A source or required configuration file cannot be read.
        metadata.PackageNotFoundError: A required quality tool is not installed.

    Notes:
        Includes every JSON/YAML configuration under configs so a policy change
        invalidates the cached result even when Python files are unchanged.
    """
    digest = hashlib.sha256()
    configuration = [
        PROJECT_ROOT / name
        for name in (
            "pyproject.toml",
            ".flake8",
            "requirements.txt",
            "requirements-dev.txt",
            "requirements.in",
            "requirements-dev.in",
            "AGENTS.md",
            "scripts/check_quality.sh",
            "scripts/run_project.sh",
            "scripts/setup_environment.sh",
            ".githooks/pre-commit",
            ".githooks/pre-push",
            ".github/workflows/quality.yml",
        )
    ]
    configuration.extend(
        sorted(
            path
            for path in (PROJECT_ROOT / "configs").rglob("*")
            if path.is_file() and path.suffix in {".json", ".yaml", ".yml"}
        )
    )
    configuration.extend(sorted((PROJECT_ROOT / "sql").rglob("*.sql")))
    for path in sources + configuration:
        digest.update(str(path.relative_to(PROJECT_ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    for tool in QUALITY_TOOLS:
        digest.update(metadata.version(tool).encode("utf-8"))
    return digest.hexdigest()


def _run_tool(name: str, command: list[str], logs: Path) -> int:
    """Execute a quality tool and save its complete output.

    Args:
        name: Tool label used for the log file and console status.
        command: Executable and arguments of the tool.
        logs: Existing directory receiving the tool log.

    Returns:
        The tool exit code; zero indicates success.

    Raises:
        OSError: The command cannot start or the log cannot be written.

    Notes:
        Prints the tool status and includes its output when the check fails.
    """
    result = subprocess.run(
        command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    content = result.stdout + result.stderr
    (logs / f"{name}.log").write_text(content, encoding="utf-8")
    print(f"{name}: {'passed' if result.returncode == 0 else 'failed'}")
    if result.returncode:
        print(content)
    return result.returncode


def main() -> int:
    """Run formatting, type, quality, and independent test scenarios.

    Returns:
        Zero when every required check succeeds; nonzero otherwise.

    Notes:
        Explicit formatting changes source files; normal checks only save logs.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", action="store_true")
    parser.add_argument("--force", action="store_true")
    options = parser.parse_args()
    logs = PROJECT_ROOT / ".cache/quality"
    logs.mkdir(parents=True, exist_ok=True)
    os.environ["BLACK_CACHE_DIR"] = str(PROJECT_ROOT / ".cache/black")
    os.environ["MYPY_CACHE_DIR"] = str(PROJECT_ROOT / ".cache/mypy")
    sources = _sources()
    directories = list(SOURCE_DIRECTORIES)
    if options.format:
        for tool in ("isort", "black"):
            if _run_tool(tool, [sys.executable, "-m", tool, *directories], logs):
                return 1
    git_report = check_git_files()
    if git_report["issues"]:
        for git_issue in git_report["issues"]:
            print(git_issue)
        return 1
    fingerprint = _fingerprint(sources)
    cached = logs / "last_success.json"
    if not options.force and not options.format and cached.is_file():
        previous = json.loads(cached.read_text(encoding="utf-8"))
        if previous.get("fingerprint") == fingerprint:
            print("Quality already passed for these exact sources and tool versions.")
            return 0
    issues = [issue for path in sources for issue in audit_source(path)]
    if issues:
        for issue in issues:
            print(f"{issue.path}:{issue.line}: {issue.message}")
        return 1
    commands = [
        ("isort", [sys.executable, "-m", "isort", "--check-only", *directories]),
        ("black", [sys.executable, "-m", "black", "--check", *directories]),
        ("flake8", [sys.executable, "-m", "flake8", *directories]),
        ("mypy", [sys.executable, "-m", "mypy"]),
        ("pylint", [sys.executable, "-m", "pylint", *directories]),
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ]
    outcomes: dict[str, int] = {}
    for name, command in commands:
        outcomes[name] = _run_tool(name, command, logs)
    report = {
        "status": "passed" if not any(outcomes.values()) else "failed",
        "checked_at_utc": utc_timestamp(),
        "fingerprint": fingerprint,
        "python_file_count": len(sources),
        "checks": outcomes,
        "tools": {tool: metadata.version(tool) for tool in QUALITY_TOOLS},
        "document_specific_issues": [asdict(issue) for issue in issues],
        "git_files": git_report,
    }
    write_json(logs / "latest_report.json", report)
    if any(outcomes.values()):
        return 1
    write_json(cached, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
