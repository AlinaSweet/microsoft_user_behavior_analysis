"""Run complete-record EDA, intermediates, frozen latent models and feature
snapshots."""

import argparse
import json
from pathlib import Path

from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.service.feature_base import build_complete_base
from user_behavior_analysis.service.feature_eda import run_feature_eda
from user_behavior_analysis.service.feature_eda_evidence import extend_feature_eda
from user_behavior_analysis.service.feature_eda_reporting import publish_feature_eda
from user_behavior_analysis.service.feature_latent_fit import fit_frozen_latent
from user_behavior_analysis.service.feature_pipeline import build_feature_snapshot
from user_behavior_analysis.service.feature_reporting import create_feature_delivery
from user_behavior_analysis.service.feature_snapshots import build_statistical_tables
from user_behavior_analysis.service.feature_snapshots import create_history_view


def main() -> int:
    """Run requested feature-system phases with reusable completion records.

    Returns:
        Zero after all requested data construction and reporting phases complete.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/feature_system.json")
    parser.add_argument(
        "--phase",
        choices=("all", "eda", "base", "latent", "snapshots", "reports"),
        default="all",
    )
    args = parser.parse_args()
    settings = load_feature_settings(Path(args.config))
    if args.phase in ("all", "eda"):
        run_feature_eda(settings)
    if args.phase in ("all", "base"):
        build_complete_base(settings)
    if args.phase in ("all", "latent", "snapshots"):
        for anchor in settings.options["anchors"]:
            directory = settings.output_dir / "snapshots" / anchor
            directory.mkdir(parents=True, exist_ok=True)
            if (directory / "statistics_state.json").exists():
                continue
            with feature_connection(
                settings, directory / "features.duckdb"
            ) as connection:
                history = create_history_view(connection, settings, anchor)
                definitions = build_statistical_tables(
                    connection, settings, anchor, history
                )
            write_json(
                directory / "statistics_state.json",
                {
                    "anchor": anchor,
                    "definitions": definitions,
                    "history": {
                        key: value
                        for key, value in history.items()
                        if key != "parameters"
                    },
                },
            )
        fit_frozen_latent(settings)
    if args.phase in ("all", "snapshots"):
        for anchor in settings.options["anchors"]:
            build_feature_snapshot(settings, anchor)
    if args.phase in ("all", "reports"):
        extend_feature_eda(settings)
        publish_feature_eda(settings)
        print(
            json.dumps(create_feature_delivery(settings), ensure_ascii=False, indent=2)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
