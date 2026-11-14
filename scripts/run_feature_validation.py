"""Build pair samples, fit grouped screening and run temporal LR ablations."""

import argparse
from pathlib import Path

from threadpoolctl import threadpool_limits  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.validation_repository import load_validation_settings
from user_behavior_analysis.models.validation_models import ValidationSettings
from user_behavior_analysis.service.sample_pipeline import build_samples
from user_behavior_analysis.service.validation_diagnostics import (
    audit_prediction_replay,
)
from user_behavior_analysis.service.validation_diagnostics import audit_training_groups
from user_behavior_analysis.service.validation_experiments import run_experiments
from user_behavior_analysis.service.validation_reporting import write_validation_report
from user_behavior_analysis.service.validation_selection import run_selection


def _audit(settings: ValidationSettings) -> dict[str, object]:
    """Run full training-cohort diagnostics and direct probability replay.

    Args:
        settings: Existing immutable validation artifacts.

    Returns:
        Both independently saved audit results.
    """
    return {
        "groups": audit_training_groups(settings),
        "replay": audit_prediction_replay(settings),
    }


def main() -> int:
    """Run explicit immutable phases and retain failed-state evidence.

    Returns:
        Zero after the requested phase succeeds.

    Raises:
        Exception: Phase failures are recorded and re-raised without suppression.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/feature_validation.json")
    parser.add_argument(
        "--phase",
        choices=["all", "samples", "selection", "experiments", "audit", "report"],
        default="all",
    )
    args = parser.parse_args()
    settings = load_validation_settings(Path(args.config))
    operations = {
        "samples": build_samples,
        "selection": run_selection,
        "experiments": run_experiments,
        "audit": _audit,
        "report": write_validation_report,
    }
    phases = list(operations) if args.phase == "all" else [args.phase]
    if settings.catalog.exists():
        raise FileExistsError(
            "Registered delivery is immutable; use a new configuration"
        )
    completed = {
        "samples": "samples.json",
        "selection": "selection.json",
        "experiments": "experiments.json",
    }
    for phase in phases:
        if phase in completed and (settings.report_dir / completed[phase]).exists():
            raise FileExistsError("Completed phase is immutable: " + phase)
        try:
            with threadpool_limits(limits=1):
                operations[phase](settings)
        except Exception as error:
            settings.report_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                settings.report_dir / (phase + "_failure.json"),
                {
                    "status": "failed",
                    "time": utc_timestamp(),
                    "error": repr(error),
                },
            )
            raise
        print("Passed phase: " + phase, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
