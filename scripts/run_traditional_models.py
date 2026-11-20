"""Train and compare three traditional models on the approved time backtest."""

import argparse
from pathlib import Path

from user_behavior_analysis.dao.traditional_repository import load_traditional_settings
from user_behavior_analysis.service.stage3_traditional import run_traditional_models


def main() -> int:
    """Run the versioned 3.2 training, tuning and independent test evaluation.

    Returns:
        Zero after writing the comparison evidence and registering local artifacts.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/stage3_traditional.json")
    )
    run_traditional_models(load_traditional_settings(parser.parse_args().config))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
