"""Build and compare the stage-three purchase prediction sample protocols."""

import argparse
from pathlib import Path

from user_behavior_analysis.dao.sampling_repository import load_sampling_settings
from user_behavior_analysis.service.stage3_sampling import run_sampling


def main() -> int:
    """Run registered sample production and the train-only strategy comparison.

    Returns:
        Zero after all data, evaluation, and reporting checks pass.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/stage3_sampling.json")
    )
    settings = load_sampling_settings(parser.parse_args().config)
    run_sampling(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
