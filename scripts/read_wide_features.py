"""Preview a bounded selection from registered wide feature snapshots."""

import argparse
from pathlib import Path

from user_behavior_analysis.dao.wide_repository import iter_wide_features


def main() -> int:
    """Read only requested columns and print a deliberately limited preview.

    Returns:
        Zero after reading the selected cutoff through the validated interface.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="data/catalog/prejoined_wide_v1.json")
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--columns", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("Preview limit must be between 1 and 100")
    remaining = args.limit
    for batch in iter_wide_features(Path(args.catalog), args.anchor, args.columns):
        selected = batch.slice(0, remaining)
        print(selected.to_pandas().to_string(index=False))
        remaining -= selected.num_rows
        if remaining <= 0:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
