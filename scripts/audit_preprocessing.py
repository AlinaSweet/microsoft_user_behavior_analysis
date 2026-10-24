"""Audit processed events, every aggregate cell, and predecessor cleaning evidence."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import cast

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.config import load_config
from user_behavior_analysis.models.preprocessing_models import PreprocessingReport
from user_behavior_analysis.service.aggregate_audit import audit_aggregate_values
from user_behavior_analysis.service.dataset_audit import DatasetAuditRequest
from user_behavior_analysis.service.dataset_audit import audit_parquet


def _predecessor_audit(output: Path) -> tuple[int, str]:
    """Run the complete cleaning audit and capture its process output.

    Args:
        output: Destination passed to the cleaning auditor for its JSON report.

    Returns:
        The child exit code and combined standard output and standard error.

    Raises:
        OSError: The audit subprocess cannot be started.

    Notes:
        A failed child audit is returned as a nonzero code, not raised here.
    """
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv/bin/python"),
            str(PROJECT_ROOT / "scripts/audit_cleaning.py"),
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    """Recompute current aggregates and recheck the previous cleaning task.

    Returns:
        Zero only after every complete-data and predecessor gate passes.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report", default="outputs/reports/stage1_step4/preprocessing.json"
    )
    parser.add_argument("--output", default="outputs/reports/stage1_step4/audit.json")
    arguments = parser.parse_args()
    report_path = input_file_path(arguments.report)
    report = cast(
        PreprocessingReport, json.loads(report_path.read_text(encoding="utf-8"))
    )
    cleaning = json.loads(
        (PROJECT_ROOT / "outputs/reports/stage1_step3/quality.json").read_text(
            encoding="utf-8"
        )
    )
    configuration = load_config()
    output = project_output_path(
        os.path.commonpath(
            [str(project_output_path(entry["path"])) for entry in report["files"]]
        )
    )
    events = audit_parquet(
        configuration,
        DatasetAuditRequest(
            output / "events",
            ("user_id", "item_id", "behavior_type", "event_time"),
            report["source_rows"],
            report["source_rows"],
            {
                "user_id": cleaning["profile"]["users"],
                "item_id": cleaning["profile"]["items"],
                "category_id": cleaning["profile"]["categories"],
            },
        ),
    )
    aggregates = [
        audit_parquet(
            configuration,
            DatasetAuditRequest(
                output / "aggregates" / table["name"],
                tuple(table["keys"]),
                table["rows"],
                table["rows"],
                {},
            ),
        )
        for table in report["aggregates"]
    ]
    values = audit_aggregate_values(
        configuration, output / "events", output / "aggregates"
    )
    file_checks = [
        {
            "path": entry["path"],
            "matches": (
                path.is_file()
                and path.stat().st_size == entry["size_bytes"]
                and sha256_file(path) == entry["sha256"]
            ),
        }
        for entry in report["files"]
        for path in [project_output_path(entry["path"])]
    ]
    predecessor_path = project_output_path(arguments.output).with_name(
        "predecessor_cleaning_audit.json"
    )
    previous_status, previous_output = _predecessor_audit(predecessor_path)
    checks = {
        "complete_event_relation": events["status"] == "passed",
        "complete_aggregate_keys": all(
            item["status"] == "passed" for item in aggregates
        ),
        "every_aggregate_value": all(item["status"] == "passed" for item in values),
        "all_artifact_fingerprints": all(item["matches"] for item in file_checks),
        "canonical_values_match_original_cleaning": (
            report["input_value_sha256"]
            == report["output_value_sha256"]
            == cleaning["output_integrity"]["exported_value_sha256"]
        ),
        "same_rows_in_all_read_trials": all(
            trial["rows"] == report["source_rows"] for trial in report["read_trials"]
        ),
        "previous_cleaning_and_research_rechecked": previous_status == 0,
    }
    evidence = {
        "status": "passed" if all(checks.values()) else "failed",
        "checked_at_utc": utc_timestamp(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "preprocessing_report_sha256": sha256_file(report_path),
        "checks": checks,
        "events": events,
        "aggregate_keys": aggregates,
        "aggregate_values": values,
        "file_checks": file_checks,
        "predecessor_audit": str(predecessor_path.relative_to(PROJECT_ROOT)),
        "predecessor_process_exit_code": previous_status,
        "predecessor_process_output": previous_output,
    }
    write_json(arguments.output, evidence)
    print(
        json.dumps(
            {"status": evidence["status"], "checks": checks},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
