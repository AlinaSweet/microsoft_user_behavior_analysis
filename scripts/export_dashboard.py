"""Export bounded full-source EDA views for the public static dashboard."""

import json
from pathlib import Path
from typing import Any

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.models.dashboard_models import DashboardFilter
from user_behavior_analysis.service.interactive_eda import COHORTS
from user_behavior_analysis.service.interactive_eda import query_dashboard

OUTPUT = PROJECT_ROOT / "outputs/reports/dashboard_publication_20261117"


def _write_view(label: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Describe a reconciled view without exposing individual event rows.

    Args:
        label: Human-readable saved-filter description.
        path: Existing or newly generated aggregate JSON.
        payload: Full-source dashboard response.

    Returns:
        Relative path, content hash, filters and record reconciliation.

    Raises:
        ValueError: Daily or behavioral totals disagree with the overview.
    """
    records = payload["overview"]["records"]
    if any(
        sum(row["records"] for row in payload[key]) != records
        for key in ("daily", "behaviors")
    ):
        raise ValueError("Dashboard aggregate totals disagree")
    return {
        "label": label,
        "path": path.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256_file(path),
        "filters": payload["filters"],
        "records": records,
    }


def main() -> None:
    """Freeze selected full-data views; retain existing measured reports unchanged.

    Raises:
        FileExistsError: This dated publication has already been completed.
        ValueError: Aggregate record reconciliation fails.
    """
    manifest = OUTPUT / "manifest.json"
    if manifest.exists():
        raise FileExistsError("Create a new dated publication for another export")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    views = []
    baseline: dict[str, Any] = {}
    for filename, label in (
        ("eda_baseline.json", "全周期 · 全部用户 / 全部类目"),
        ("eda_mature_example.json", "成熟随访 · 11月18日—12月8日 / 全部用户"),
    ):
        path = PROJECT_ROOT / "outputs/reports/stage2" / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        views.append(_write_view(label, path, payload))
        if filename == "eda_baseline.json":
            baseline = payload
    labels = {
        "low_activity": "低活跃",
        "high_activity": "高活跃",
        "new_observed": "新近观测",
        "high_value_proxy": "高价值代理",
        "potential_proxy": "潜力代理",
        "at_risk_proxy": "近期风险代理",
        "dormant_proxy": "沉睡代理",
    }
    requests = [
        (
            "全周期 · " + labels[cohort],
            DashboardFilter("2025-11-18", "2025-12-18", cohort, "", ""),
        )
        for cohort in COHORTS
        if cohort != "all"
    ]
    for start, end in (
        ("2025-11-18", "2025-11-24"),
        ("2025-11-25", "2025-12-01"),
        ("2025-12-02", "2025-12-08"),
    ):
        requests.append(
            (
                start + "—" + end + " · 全部用户",
                DashboardFilter(start, end, "all", "", ""),
            )
        )
    for row in baseline["categories"][:5]:
        category = row["category_id"]
        requests.append(
            (
                "全周期 · 热门类目 " + str(category),
                DashboardFilter("2025-11-18", "2025-12-18", "all", category, ""),
            )
        )
    source = PROJECT_ROOT / "data/processed/base_raw_v2/key_hour/data.parquet"
    source_hash = sha256_file(source)
    for index, (label, request) in enumerate(requests):
        path = OUTPUT / ("view_" + str(index + 1).zfill(2) + ".json")
        payload = query_dashboard(request)
        path.write_text(
            json.dumps(
                payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            )
            + "\n",
            encoding="utf-8",
        )
        views.append(_write_view(label, path, payload))
        print(label + ": " + str(payload["overview"]["records"]), flush=True)
    if sha256_file(source) != source_hash:
        raise ValueError("Source changed during dashboard export")
    manifest.write_text(
        json.dumps(
            {
                "version": "dashboard_publication_20261117",
                "mode": "saved_full_source_views",
                "source_categories": baseline["overview"]["categories"],
                "source": "data/processed/base_raw_v2/key_hour/data.parquet",
                "source_sha256": source_hash,
                "views": views,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Saved " + str(len(views)) + " reconciled views", flush=True)


if __name__ == "__main__":
    main()
