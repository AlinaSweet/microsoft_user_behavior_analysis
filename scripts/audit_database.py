"""Audit complete database/SQL exports and recheck the previous first stage."""

import argparse
import json
import logging
import subprocess
import sys
from typing import cast

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.sqlite_client import QUERY_NAMES
from user_behavior_analysis.dao.sqlite_client import query_path
from user_behavior_analysis.models.database_models import DatabaseAnalysisReport
from user_behavior_analysis.models.database_models import DatabaseReport
from user_behavior_analysis.service.database_audit import audit_database_values
from user_behavior_analysis.service.database_audit import audit_query_exports

LOGGER = logging.getLogger(__name__)


def main() -> int:
    """Compare full native data and run a fresh previous-stage audit.

    Returns:
        Zero only when complete values, artifacts, and predecessor gates pass.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-report", default="outputs/reports/stage2_step1/database.json"
    )
    parser.add_argument(
        "--analysis-report", default="outputs/reports/stage2_step1/analysis.json"
    )
    parser.add_argument("--output-dir", required=True)
    arguments = parser.parse_args()
    output = project_output_path(arguments.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    build_path = input_file_path(arguments.database_report)
    analysis_path = input_file_path(arguments.analysis_report)
    build = cast(DatabaseReport, json.loads(build_path.read_text(encoding="utf-8")))
    analysis = cast(
        DatabaseAnalysisReport, json.loads(analysis_path.read_text(encoding="utf-8"))
    )
    database = project_output_path(build["database_path"])
    LOGGER.info("Comparing complete source cells with native SQLite rows")
    values = audit_database_values(build["source_catalog"], database)
    exports = audit_query_exports(database, analysis)
    LOGGER.info("Rechecking the complete previous first stage")
    previous = subprocess.run(
        [
            sys.executable,
            "scripts/audit_stage1.py",
            "--output-dir",
            str(output / "previous_stage1"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    log = output / "previous_stage1.log"
    log.write_text(previous.stdout + previous.stderr, encoding="utf-8")
    checks = {
        "database_report_passed": build["status"] == "passed"
        and all(build["checks"].values()),
        "analysis_report_passed": analysis["status"] == "passed"
        and all(analysis["checks"].values()),
        "registered_source_catalog_unchanged": (
            sha256_file(input_file_path(build["source_catalog"]))
            == build["source_catalog_sha256"]
        ),
        "database_fingerprint_and_path": (
            sha256_file(database)
            == build["database_sha256"]
            == analysis["database_sha256"]
            and build["database_path"] == analysis["database_path"]
        ),
        "every_native_source_value": values["status"] == "passed",
        "all_eleven_queries": {item["name"] for item in exports} == set(QUERY_NAMES),
        "all_exported_query_values": all(
            item["status"] == "passed" for item in exports
        ),
        "all_query_sources_unchanged": (
            set(analysis["query_sha256"]) == set(QUERY_NAMES)
            and all(
                sha256_file(query_path(name)) == analysis["query_sha256"][name]
                for name in QUERY_NAMES
            )
        ),
        "previous_complete_stage": previous.returncode == 0,
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "checked_at_utc": utc_timestamp(),
        "auditor_code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "build_report_sha256": sha256_file(build_path),
        "analysis_report_sha256": sha256_file(analysis_path),
        "checks": checks,
        "native_source_values": values,
        "query_exports": exports,
        "previous_stage_audit": str(
            (output / "previous_stage1/audit.json").relative_to(PROJECT_ROOT)
        ),
        "previous_stage_exit_code": previous.returncode,
        "previous_stage_log_sha256": sha256_file(log),
    }
    write_json(output / "audit.json", report)
    print(json.dumps({"status": report["status"], "checks": checks}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    raise SystemExit(main())
