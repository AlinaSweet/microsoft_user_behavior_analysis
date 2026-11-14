"""Load validated experiment contracts and stream immutable sample parts."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.validation_models import ValidationSettings
from user_behavior_analysis.service.wide_contracts import require_contract


def load_validation_settings(path: Path) -> ValidationSettings:
    """Validate time-ordered splits and project-confined new output locations.

    Args:
        path: Existing JSON configuration.

    Returns:
        Checked locations and options.

    Raises:
        ValueError: A split, bound, path or experiment is invalid.
    """
    raw = read_json_object(path)
    names = ["wide_catalog", "label_root", "sample_root", "report_dir", "catalog"]
    paths = {name: project_output_path(raw.pop(name)) for name in names}
    splits = raw["splits"]
    dates = [pd.Timestamp(splits[name]) for name in ("train", "validation", "test")]
    require_contract(list(splits) == ["train", "validation", "test"], "Split names")
    require_contract(raw["label_days"] == 7, "Seven-day labels required")
    require_contract(
        all(
            left + pd.Timedelta(days=7) <= right
            for left, right in zip(dates, dates[1:])
        ),
        "Labels overlap the next prediction cutoff",
    )
    require_contract(1 <= raw["epochs"] <= 20, "Epoch bound")
    require_contract(1024 <= raw["batch_rows"] <= 32768, "Batch bound")
    require_contract(1000 <= raw["selection_rows"] <= 200000, "Selection sample bound")
    require_contract(0 < raw["missing_limit"] <= 1, "Missing threshold")
    require_contract(0 < raw["correlation_limit"] <= 1, "Correlation threshold")
    require_contract(raw["alpha"] > 0, "Positive regularization required")
    require_contract(0 < raw["decision_threshold"] < 1, "Classification threshold")
    allowed = set(raw["maximum_features"])
    require_contract(
        all(set(groups) <= allowed for groups in raw["experiments"].values()),
        "Unknown experiment group",
    )
    return ValidationSettings(**paths, options=raw)


def iter_sample_frames(
    parts: list[dict[str, Any]], columns: list[str], batch_rows: int = 8192
) -> Iterator[pd.DataFrame]:
    """Read already verified sample files using bounded column projection.

    Args:
        parts: Fingerprinted sample records verified at phase entry.
        columns: Registered columns required by this operation.
        batch_rows: Maximum decoded rows in each frame.

    Yields:
        Ordered pandas frames without filling missing values.
    """
    for part in parts:
        path = project_output_path(part["path"])
        for batch in pq.ParquetFile(path).iter_batches(
            batch_size=batch_rows, columns=columns
        ):
            yield batch.to_pandas()


def verified_sample_manifest(settings: ValidationSettings) -> dict[str, Any]:
    """Reject changed inputs before fitting or evaluation.

    Args:
        settings: Completed label/sample phase locations.

    Returns:
        Passed sample manifest after checking every file fingerprint.

    Raises:
        ValueError: The phase failed or any source/sample was changed.
    """
    record = read_json_object(settings.report_dir / "samples.json")
    require_contract(record.get("status") == "passed", "Samples did not pass")
    for item in record["inputs"]:
        verify_registered_file(item)
    for snapshot in record["snapshots"]:
        verify_registered_file(snapshot["target_file"])
        for part in snapshot["sample_parts"]:
            verify_registered_file(part)
    return record
