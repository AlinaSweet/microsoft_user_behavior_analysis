"""Run dashboard-one EDA and publish local reports without changing source facts."""

import argparse
import json
from pathlib import Path

from user_behavior_analysis.dao.eda_repository import build_eda_cache
from user_behavior_analysis.dao.eda_repository import load_eda_settings
from user_behavior_analysis.service.eda_analysis import collect_eda
from user_behavior_analysis.service.eda_reporting import render_saved_eda


def main() -> int:
    """Materialize exploratory tables and record source/counting provenance.

    Returns:
        Zero after full analytical tables and their local metadata are saved.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/eda_dashboard1.json")
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()
    settings = load_eda_settings(Path(args.config))
    if args.render_only:
        render_saved_eda(settings)
        return 0
    metadata = build_eda_cache(settings)
    metrics, tables = collect_eda(settings, metadata)
    report_dir = settings["report_dir"]
    report_dir.mkdir(parents=True, exist_ok=True)
    public = {}
    local_names = {"users", "latest_cohort", "item_quadrants"}
    for name, frame in tables.items():
        if name in local_names:
            frame.to_parquet(settings["cache_dir"] / (name + ".parquet"), index=False)
        else:
            public[name] = json.loads(
                frame.to_json(orient="records", force_ascii=False)
            )
    payload = {"metadata": metadata, "metrics": metrics, "tables": public}
    (report_dir / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    render_saved_eda(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
