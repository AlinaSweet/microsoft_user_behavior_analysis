"""Run the sequence-model and stacking stages with matched temporal samples."""

import argparse
from pathlib import Path

from user_behavior_analysis.dao.sequence_repository import load_advanced_settings
from user_behavior_analysis.service.stage3_deep import run_deep_models
from user_behavior_analysis.service.stage3_ensemble import run_ensemble


def main() -> int:
    """Run the requested advanced modeling stages in temporal order.

    Returns:
        Zero after the requested catalogs and aggregate reports have been verified.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/stage3_advanced.json", type=Path)
    parser.add_argument("--phase", choices=("all", "deep", "ensemble"), default="all")
    args = parser.parse_args()
    settings = load_advanced_settings(args.config)
    if args.phase in ("all", "deep"):
        run_deep_models(settings)
    if args.phase in ("all", "ensemble"):
        run_ensemble(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
