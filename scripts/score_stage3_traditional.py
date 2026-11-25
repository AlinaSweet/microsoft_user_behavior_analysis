"""Run the conventional base models in a separate CPU worker."""

import argparse
from pathlib import Path

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.service.ensemble_traditional import (
    export_traditional_scores,
)


def main() -> int:
    """Export checked scores from an explicitly permitted time split.

    Returns:
        Zero after the new local score bundle is written.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sampling_catalog", type=Path)
    parser.add_argument("traditional_catalog", type=Path)
    parser.add_argument("split", choices=("validation", "test"))
    parser.add_argument("output", type=Path)
    parser.add_argument("case_count", type=int)
    parser.add_argument("seed", type=int)
    args = parser.parse_args()
    export_traditional_scores(
        args.sampling_catalog,
        args.traditional_catalog,
        args.split,
        project_output_path(args.output),
        (args.case_count, args.seed),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
