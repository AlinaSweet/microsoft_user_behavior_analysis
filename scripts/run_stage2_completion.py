"""Reproduce remaining stage-two preprocessing, comparisons and current reports."""

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.dao.completion_repository import load_completion_settings
from user_behavior_analysis.service.completion_audit import audit_completion
from user_behavior_analysis.service.completion_experiments import (
    run_completion_experiments,
)
from user_behavior_analysis.service.completion_pipeline import prepare_completion
from user_behavior_analysis.service.stage2_reporting import write_stage2_report


def main() -> int:
    """Run explicitly chosen stages into a new immutable completion version.

    Returns:
        Zero after every requested stage succeeds.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/stage2_delivery.json")
    parser.add_argument(
        "--phase",
        choices=["all", "prepare", "experiments", "reports", "audit"],
        default="all",
    )
    args = parser.parse_args()
    settings = load_completion_settings(Path(args.config))
    if settings.catalog.exists():
        raise FileExistsError(
            ("Registered completion is immutable; choose ne" + "w version paths")
        )
    operations = {
        "prepare": prepare_completion,
        "experiments": run_completion_experiments,
        "reports": write_stage2_report,
        "audit": audit_completion,
    }
    for phase in operations if args.phase == "all" else [args.phase]:
        with threadpool_limits(limits=1):
            operations[phase](settings)
        print("Passed completion phase: " + phase, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
