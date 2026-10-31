"""Typed settings shared by the exploratory analysis and report layers."""

from pathlib import Path
from typing import TypedDict


class EDASettings(TypedDict):
    """Validated project locations, observation windows and support thresholds."""

    database: Path
    cache_dir: Path
    report_dir: Path
    anchors: list[str]
    history_days: int
    label_days: int
    transition_max_gap_hours: int
    min_item_view_pairs: int
    min_category_view_pairs: int
    quadrant_min_view_pairs: int
