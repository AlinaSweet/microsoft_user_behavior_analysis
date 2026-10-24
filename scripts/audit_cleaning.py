"""Recheck a complete cleaning run and its predecessor evidence."""

import argparse
import json
import re
import subprocess
from typing import cast

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.config import load_config
from user_behavior_analysis.dao.artifact_repository import check_git_files
from user_behavior_analysis.dao.source_repository import source_declaration_status
from user_behavior_analysis.models.cleaning_models import CleaningReport
from user_behavior_analysis.service.anomaly_audit import audit_activity_anomalies
from user_behavior_analysis.service.dataset_audit import DatasetAuditRequest
from user_behavior_analysis.service.dataset_audit import audit_parquet

RESEARCH_FILES = [
    "docs/research/README.md",
    "docs/research/literature_review.md",
    "docs/research/tech_stack_comparison.md",
    "docs/research/feature_engineering_plan.md",
    "docs/research/experiment_plan.md",
    "docs/research/references.json",
    "docs/research/references.bib",
]


def _predecessor_checks(reference: str) -> dict[str, bool]:
    """Compare research artifacts with their reviewed Git and paper baselines.

    Args:
        reference: Git commit or ref containing the reviewed research documents.

    Returns:
        Pass flags for five paper hashes, unchanged documents, 26 features,
        and ten planned experiments.

    Raises:
        subprocess.CalledProcessError: A Git reference or stored file is unavailable.
        OSError: A local reference document or cached paper cannot be read.
        ValueError: The reference inventory cannot be decoded as JSON.
    """
    reference = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", reference + "^{commit}"],
        cwd=PROJECT_ROOT,
        text=True,
    ).strip()
    references = json.loads(
        (PROJECT_ROOT / "docs/research/references.json").read_text(encoding="utf-8")
    )
    papers = all(
        sha256_file(PROJECT_ROOT / ".cache/research" / (paper["paper_id"] + ".pdf"))
        == paper["sha256"]
        for paper in references["papers"]
    )
    unchanged = all(
        subprocess.check_output(
            ["git", "show", reference + ":" + name], cwd=PROJECT_ROOT
        )
        == (PROJECT_ROOT / name).read_bytes()
        for name in RESEARCH_FILES
    )
    feature_text = (
        PROJECT_ROOT / "docs/research/feature_engineering_plan.md"
    ).read_text(encoding="utf-8")
    section = feature_text.split("## 3. 规划特征字典", 1)[1].split("## 4.", 1)[0]
    features = re.findall(r"^\| ([a-z][a-z0-9_]+) \|", section, re.MULTILINE)
    experiments = re.findall(
        r"^\| (e\d{2}) \|",
        (PROJECT_ROOT / "docs/research/experiment_plan.md").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return {
        "five_paper_fingerprints": len(references["papers"]) == 5 and papers,
        "research_documents_match_reviewed_commit": unchanged,
        "twenty_six_unique_feature_definitions": len(features)
        == len(set(features))
        == 26,
        "ten_unique_planned_experiments": len(experiments)
        == len(set(experiments))
        == 10,
    }


def main() -> int:
    """Run independent full-data, artifact, and predecessor checks.

    Returns:
        Zero only when every declared audit gate passes.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="outputs/reports/stage1_step3/quality.json")
    parser.add_argument("--output", default="outputs/reports/stage1_step3/audit.json")
    parser.add_argument("--previous-review-commit", default="ba7afad")
    arguments = parser.parse_args()
    report_path = input_file_path(arguments.report)
    report = cast(CleaningReport, json.loads(report_path.read_text(encoding="utf-8")))
    config = load_config()
    counts = report["row_accounting"]
    key = ("user_id", "item_id", "behavior_type", "event_time")
    directory = PROJECT_ROOT / report["output_dir"]
    source_audit = audit_parquet(
        config,
        DatasetAuditRequest(
            directory / "validated",
            key,
            counts["valid_before_deduplication"],
            counts["clean_rows"] + counts["conflicting_keys"],
            {},
        ),
    )
    profile = report["profile"]
    clean_audit = audit_parquet(
        config,
        DatasetAuditRequest(
            directory / "events",
            key,
            counts["clean_rows"],
            counts["clean_rows"],
            {
                "user_id": profile["users"],
                "item_id": profile["items"],
                "category_id": profile["categories"],
            },
        ),
    )
    anomaly_audits = audit_activity_anomalies(
        config, directory / "events", report["anomalies"]
    )
    files_match = all(
        path.is_file()
        and path.stat().st_size == entry["size_bytes"]
        and sha256_file(path) == entry["sha256"]
        for entry in report["files"]
        for path in [project_output_path(entry["path"])]
    )
    source_hash = sha256_file(input_file_path(report["source_path"]))
    source_manifest = json.loads(
        (PROJECT_ROOT / "data/catalog/user_behavior_raw.json").read_text(
            encoding="utf-8"
        )
    )
    predecessor = _predecessor_checks(arguments.previous_review_commit)
    environment = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), "-m", "pip", "check"],
        capture_output=True,
        text=True,
        check=False,
    )
    provenance = json.loads(
        (PROJECT_ROOT / "data/catalog/data_provenance.json").read_text(encoding="utf-8")
    )
    checks = {
        "full_validated_relation": source_audit["status"] == "passed",
        "full_clean_relation": clean_audit["status"] == "passed",
        "independent_anomaly_thresholds": all(
            item["status"] == "passed" for item in anomaly_audits
        ),
        "all_parquet_fingerprints": files_match,
        "source_matches_registered_and_run_fingerprints": (
            source_hash
            == source_manifest["sha256"]
            == report["source_sha256_before"]
            == report["source_sha256_after"]
        ),
        "row_accounting": counts["reconciled"],
        "export_values": report["output_integrity"]["values_match"],
        "source_use_declaration_recorded": (
            provenance.get("source_sha256") == source_hash
            and provenance.get("local_processing_authorized") is True
        ),
        "predecessor_research": all(predecessor.values()),
        "environment_dependency_consistency": environment.returncode == 0,
        "git_file_policy": not check_git_files()["issues"],
    }
    evidence = {
        "status": "passed" if all(checks.values()) else "failed",
        "checked_at_utc": utc_timestamp(),
        "auditor_code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "cleaning_code_commit": report["code_commit"],
        "cleaning_report_sha256": sha256_file(report_path),
        "scope": (
            "Full validated and cleaned data; all artifact hashes; "
            + "prior engineering/research"
        ),
        "checks": checks,
        "validated_relation": source_audit,
        "clean_relation": clean_audit,
        "anomaly_audits": anomaly_audits,
        "parquet_files_checked": len(report["files"]),
        "predecessor_review_commit": arguments.previous_review_commit,
        "predecessor_research_checks": predecessor,
        "source_declaration_status_current": source_declaration_status(source_hash),
        "historical_provenance_note": (
            "quality.json preserves the earlier implementation's pending-declaration "
            + "text; this audit records the subsequently supplied user declaration."
        ),
        "dependency_check": environment.stdout.strip(),
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
