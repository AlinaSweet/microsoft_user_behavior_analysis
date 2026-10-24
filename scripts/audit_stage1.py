"""Recheck all four first-stage task points into a new evidence directory."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TypedDict
from typing import cast

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json


class ProcessEvidence(TypedDict):
    """Record a reproducible subprocess and its complete project-local log."""

    name: str
    command: list[str]
    exit_code: int
    log_path: str
    log_sha256: str


def _run(name: str, command: list[str], output: Path) -> ProcessEvidence:
    """Run one audit command and retain a fingerprinted process log.

    Args:
        name: Evidence label also used as the log file stem.
        command: Executable and arguments to run from the project root.
        output: Existing project-local directory receiving the log.

    Returns:
        The command, exit code, relative log path, and log SHA-256.

    Raises:
        OSError: The subprocess cannot start or its log cannot be written.
        ValueError: The log path is outside the project root.

    Notes:
        Nonzero child exit codes remain evidence for the caller to evaluate.
    """
    result = subprocess.run(
        command, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    log = output / (name + ".log")
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    return {
        "name": name,
        "command": command,
        "exit_code": result.returncode,
        "log_path": str(log.relative_to(PROJECT_ROOT)),
        "log_sha256": sha256_file(log),
    }


def _passed(path: Path) -> bool:
    """Read whether an existing JSON audit reports a passed status.

    Args:
        path: Audit report expected to contain a JSON object.

    Returns:
        True only for status passed; False for a missing file or another status.

    Raises:
        OSError: An existing report cannot be read.
        ValueError: The report is not valid JSON.
    """
    if not path.is_file():
        return False
    document = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    return document.get("status") == "passed"


def main() -> int:
    """Run fresh engineering, quality, cleaning, research, and aggregate checks.

    Returns:
        Zero only if every local first-stage verification succeeds.

    Notes:
        Requires a new output directory so historical evidence is preserved.
        Remote branch synchronization and CI are verified separately at delivery.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default="configs/audit.yaml")
    arguments = parser.parse_args()
    output = project_output_path(arguments.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    evidence = [
        _run(
            "quality",
            ["bash", "scripts/check_quality.sh", "--force"],
            output,
        )
    ]
    quality = PROJECT_ROOT / ".cache/quality/latest_report.json"
    shutil.copyfile(quality, output / "quality.json")
    evidence.append(
        _run(
            "environment",
            [
                sys.executable,
                "-m",
                "user_behavior_analysis",
                "--config",
                arguments.config,
                "check",
                "--output-dir",
                str(output / "environment"),
            ],
            output,
        )
    )
    evidence.append(
        _run(
            "preprocessing",
            [
                sys.executable,
                "scripts/audit_preprocessing.py",
                "--config",
                arguments.config,
                "--output",
                str(output / "preprocessing_audit.json"),
            ],
            output,
        )
    )
    checks = {
        "all_processes_succeeded": all(item["exit_code"] == 0 for item in evidence),
        "quality_gate": _passed(output / "quality.json"),
        "live_environment": _passed(output / "environment/environment_check.json"),
        "full_preprocessing_and_predecessors": _passed(
            output / "preprocessing_audit.json"
        ),
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "checked_at_utc": utc_timestamp(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "scope": (
            "Fresh quality and live workers; complete event/aggregate relations; "
            + "raw/artifact hashes, anomaly thresholds and reviewed research."
        ),
        "cloud_ci_scope": "Verified separately in the delivery record.",
        "checks": checks,
        "processes": evidence,
    }
    write_json(output / "audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
