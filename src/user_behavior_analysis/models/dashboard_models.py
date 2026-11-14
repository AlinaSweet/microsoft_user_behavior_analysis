"""Describe the three global EDA filters and an optional item drill-down."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardFilter:
    """Keep analysis populations explicit and independent of future labels.

    Attributes:
        start: Inclusive source calendar date.
        end: Inclusive source calendar date.
        cohort: Fixed observed-window activity or RF-proxy group.
        category: Optional exact category identifier.
        item: Optional item drill-down identifier.
    """

    start: str
    end: str
    cohort: str = "all"
    category: str = ""
    item: str = ""
