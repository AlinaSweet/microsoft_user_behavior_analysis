"""Export complete SQLite query tables and their small verification summaries."""

import argparse
import json
from pathlib import Path

from user_behavior_analysis.service.sql_analysis import run_sql_analysis


def main() -> int:
    """Run the registered queries against the preserved-record database.

    Returns:
        Zero after every export and aggregate control succeeds.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database", default="data/processed/analysis_raw_v1/behavior.sqlite"
    )
    parser.add_argument(
        "--output-dir", default="data/processed/analysis_raw_v1/sql_results"
    )
    parser.add_argument("--report-dir", default="outputs/reports/stage2_step1_20261024")
    args = parser.parse_args()
    result = run_sql_analysis(
        Path(args.database), Path(args.output_dir), Path(args.report_dir)
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "totals": result["totals"],
                "high_frequency": result["high_frequency"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
