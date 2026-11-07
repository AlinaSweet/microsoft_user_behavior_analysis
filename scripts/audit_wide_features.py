"""Audit all existing prejoined snapshots and publish a new read catalog."""

import argparse
from pathlib import Path

from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.service.wide_audit import audit_prejoined_features


def main() -> int:
    """Check every configured cutoff without rebuilding its feature values.

    Returns:
        Zero after all full-data contracts and catalog publication succeed.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/feature_system.json")
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--catalog", required=True)
    args = parser.parse_args()
    report = audit_prejoined_features(
        load_feature_settings(Path(args.config)),
        Path(args.report_dir),
        Path(args.catalog),
    )
    print("Passed: " + str(report["candidate_rows"]) + " candidate rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
