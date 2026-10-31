"""Define the configured scope of the preserved-record feature system."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import NotRequired
from typing import TypedDict


@dataclass(frozen=True)
class FeatureSettings:
    """Project-confined paths and configurable feature parameters.

    Attributes:
        source_catalog: Full validated-record catalog.
        source_database: Read-only database used for independent controls and EDA.
        base_dir: New complete-record Parquet and precomputation directory.
        output_dir: Snapshot, sequence and latent-feature directory.
        report_dir: Feature dictionary and completion evidence destination.
        eda_report_dir: Deeper exploration results preceding table design.
        options: Window, anchor, resource and interaction parameters.
    """

    source_catalog: Path
    source_database: Path
    base_dir: Path
    output_dir: Path
    report_dir: Path
    eda_report_dir: Path
    options: dict[str, Any]


class FeatureDefinition(TypedDict):
    """Describe one persisted scalar or sequence field without counting IDs."""

    table: str
    name: str
    family: str
    chinese_name: str
    calculation: str
    description: str
    window_days: int | None
    dtype: str
    missing_policy: str
    available_before_anchor: bool
    preprocessing: str
    artifact: str
    status: str
    storage_dtype: NotRequired[str]
