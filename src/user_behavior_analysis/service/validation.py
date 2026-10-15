"""Validate source records without rewriting identifiers or raw CSV values."""

from pathlib import Path

import numpy as np
import pandas as pd

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.cleaning_models import CleaningPolicy
from user_behavior_analysis.models.cleaning_models import PartitionEvidence
from user_behavior_analysis.models.cleaning_models import PartitionRequest

SOURCE_COLUMNS = ["time", "user_id", "item_id", "item_category", "behavior_type"]
EVENT_COLUMNS = [
    "event_id",
    "user_id",
    "item_id",
    "category_id",
    "behavior_type",
    "event_time",
]


def _violations(
    frame: pd.DataFrame, policy: CleaningPolicy
) -> tuple[dict[str, pd.Series], pd.Series]:
    missing = {
        f"missing_{column}": frame[column].isna()
        | frame[column].str.strip().eq("").fillna(True)
        for column in SOURCE_COLUMNS
    }
    violations = dict(missing)
    for column in ("user_id", "item_id", "item_category"):
        valid_id = frame[column].str.fullmatch(r"[^\s\x00-\x1f\x7f]+", na=False)
        violations[f"invalid_{column}"] = ~valid_id & ~missing[f"missing_{column}"]
    shape = frame["time"].str.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}", na=False)
    parsed = pd.to_datetime(frame["time"], format="%Y-%m-%d %H", errors="coerce")
    valid_time = shape & parsed.notna()
    violations["invalid_time"] = ~valid_time & ~missing["missing_time"]
    outside = parsed.ge(pd.Timestamp(policy.maximum_event_time))
    if policy.minimum_event_time is not None:
        outside |= parsed.lt(pd.Timestamp(policy.minimum_event_time))
    violations["time_outside_policy"] = outside.fillna(False)
    violations["invalid_behavior_type"] = (
        ~frame["behavior_type"].isin(policy.allowed_behaviors)
        & ~missing["missing_behavior_type"]
    )
    return violations, parsed


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression=None)


def normalize_partition(
    frame: pd.DataFrame, request: PartitionRequest
) -> PartitionEvidence:
    """Validate and persist one bounded partition inside a worker.

    Args:
        frame: Source columns stored as strings; the input is not mutated.
        request: Deterministic record ordinals, paths, and validation rules.

    Returns:
        Counts and paths for valid and rejected records.

    Raises:
        ValueError: The frame does not contain the declared source columns.

    Notes:
        Writes new Parquet files under the request directory. Statistical
        activity outliers are evaluated globally after deduplication.
    """
    if list(frame.columns) != SOURCE_COLUMNS:
        raise ValueError("Partition columns differ from the source contract")
    directory = project_output_path(request.directory)
    frame = frame.reset_index(drop=True)
    violations, parsed = _violations(frame, request.policy)
    invalid = pd.DataFrame(violations).any(axis=1)
    event_ids = np.arange(
        request.first_record, request.first_record + len(frame), dtype=np.int64
    )
    valid = (
        frame.loc[~invalid]
        .rename(columns={"item_category": "category_id", "time": "event_time"})
        .copy()
    )
    valid["event_time"] = parsed.loc[~invalid]
    valid["event_id"] = event_ids[~invalid.to_numpy()]
    valid_path = directory / "validated" / f"part_{request.partition_id:05d}.parquet"
    _write_frame(valid[EVENT_COLUMNS], valid_path)
    rejected_path = None
    if invalid.any():
        rejected = frame.loc[invalid].copy()
        rejected["event_id"] = event_ids[invalid.to_numpy()]
        reasons = pd.Series("", index=frame.index, dtype="string")
        for name, mask in violations.items():
            reasons.loc[mask] = reasons.loc[mask] + name + "|"
        rejected["failure_reasons"] = reasons.loc[invalid].str.rstrip("|")
        rejected_path = (
            directory / "rejected" / f"part_{request.partition_id:05d}.parquet"
        )
        _write_frame(rejected, rejected_path)
    return {
        "partition_id": request.partition_id,
        "input_rows": len(frame),
        "valid_rows": len(valid),
        "invalid_rows": int(invalid.sum()),
        "violation_counts": {
            name: int(mask.sum()) for name, mask in violations.items()
        },
        "valid_path": str(valid_path),
        "rejected_path": str(rejected_path) if rejected_path else None,
    }
