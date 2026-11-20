"""Refuse non-temporal samples and verify exact local prediction outputs."""

from datetime import datetime
from datetime import timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.dao.sampling_repository import load_partition
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.sampling_models import SPLITS
from user_behavior_analysis.models.sampling_models import PartitionEvidence
from user_behavior_analysis.models.traditional_models import LabeledMatrix
from user_behavior_analysis.models.traditional_models import TemporalPlan
from user_behavior_analysis.models.traditional_models import TraditionalSettings
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import require_contract


def load_traditional_settings(path: Path) -> TraditionalSettings:
    """Read the versioned experiment inputs, destinations and tuning budget.

    Args:
        path: Project-contained JSON configuration with a stage 3.1 catalog.

    Returns:
        Confined and validated configuration.
    """
    raw = read_json_object(path)
    locations = {
        name: project_output_path(raw[name])
        for name in ("sampling_catalog", "data_root", "report_dir", "catalog")
    }
    require_contract(
        all(
            not left.is_relative_to(right) and not right.is_relative_to(left)
            for left, right in combinations(locations.values(), 2)
        ),
        "Model input and destinations must be separate",
    )
    for name, minimum, maximum in (
        ("seed", 0, 2**32 - 1),
        ("trials_per_model", 4, 100),
        ("threads", 1, 16),
    ):
        value = raw[name]
        require_contract(
            isinstance(value, int)
            and not isinstance(value, bool)
            and minimum <= value <= maximum,
            "Invalid model configuration: " + name,
        )
    return TraditionalSettings(
        sampling_catalog=locations["sampling_catalog"],
        data_root=locations["data_root"],
        report_dir=locations["report_dir"],
        catalog=locations["catalog"],
        seed=raw["seed"],
        threads=raw["threads"],
        trials_per_model=raw["trials_per_model"],
    )


def check_chronology(anchors: dict[str, str]) -> None:
    """Reject label windows that would be immature at the next prediction cutoff.

    Args:
        anchors: Source-time dates for train, validation and test.

    Raises:
        ValueError: A split is missing or any label window crosses a later cutoff.
    """
    require_contract(set(anchors) == set(SPLITS), "Expected train, validation and test")
    dates = [datetime.fromisoformat(anchors[name]) for name in SPLITS]
    require_contract(
        all(left + timedelta(days=7) <= right for left, right in zip(dates, dates[1:])),
        "A seven-day label window overlaps the next prediction cutoff",
    )


def load_temporal_plan(settings: TraditionalSettings) -> TemporalPlan:
    """Read the audited time-only input and its exact prior feature whitelist.

    Args:
        settings: Checked model configuration pointing to stage 3.1 output.

    Returns:
        The chronological plan, without loading test rows.
    """
    catalog = read_json_object(settings.sampling_catalog)
    require_contract(
        catalog.get("status") == "passed"
        and catalog.get("kind") == "stage3_purchase_samples",
        "An approved stage 3.1 sampling catalog is required",
    )
    approval = read_json_object(verify_registered_file(catalog["source_manifest"]))
    require_contract(approval.get("status") == "passed", "Source sample audit failed")
    anchors = catalog["time_anchors"]
    check_chronology(anchors)
    require_contract(
        anchors == approval["splits"], "Chronology changed since source audit"
    )
    configured = read_json_object(Path("configs/stage3_sampling.json"))["features"]
    features = catalog["features"]
    definitions = {row["name"]: row for row in approval["definitions"]}
    require_contract(
        features == configured
        and len(features) == len(set(features)) > 0
        and all(
            definitions.get(name, {}).get("available_before_anchor") is True
            and definitions[name].get("window_days") == 7
            for name in features
        ),
        "Models require the approved history-only feature list from 3.1",
    )
    partitions = catalog["protocols"]["time_backtest"]
    approved = {row["anchor"]: row for row in approval["snapshots"]}
    for name in SPLITS:
        record = partitions[name]
        snapshot = approved[anchors[name]]
        require_contract(
            record["first_anchor"] == record["last_anchor"] == anchors[name]
            and snapshot["target_available"] is True
            and record["rows"] == snapshot["rows"]
            and record["positives"] == snapshot["positives"],
            "Partition does not match its approved mature time cutoff: " + name,
        )
    return TemporalPlan(
        file_record(settings.sampling_catalog), tuple(features), anchors, partitions
    )


def read_temporal_split(
    plan: TemporalPlan, split: str
) -> tuple[LabeledMatrix, dict[str, Any]]:
    """Verify each recorded cutoff and return model features without metadata.

    Args:
        plan: Validated chronological design with approved feature order.
        split: Natural chronological train, validation or test partition.

    Returns:
        The separate feature/label arrays and full-row time controls.
    """
    record = plan.partitions[split]
    path = verify_registered_file(record["file"])
    cutoff = datetime.fromisoformat(plan.anchors[split])
    end = cutoff + timedelta(days=7)
    with duckdb.connect() as connection:
        actual = require_result_row(
            connection.execute(
                "SELECT COUNT(*),COUNT(DISTINCT(user_id,item_id)),"
                + "COUNT(*) FILTER(WHERE target=1),"
                + "COUNT(*) FILTER(WHERE as_of_time IS DISTINCT FROM $cutoff "
                + "OR user_id IS NULL OR item_id IS NULL "
                + "OR pair_source_max_event_time IS NULL "
                + "OR pair_source_max_event_time >= as_of_time "
                + "OR label_start IS DISTINCT FROM $cutoff "
                + "OR label_end_exclusive IS DISTINCT FROM $end "
                + "OR target_available IS DISTINCT FROM TRUE "
                + "OR target IS NULL OR target NOT IN (0,1)),"
                + "MAX(pair_source_max_event_time) FROM read_parquet($file)",
                {"cutoff": cutoff, "end": end, "file": str(path)},
            ).fetchone()
        )
    require_contract(
        actual[:4] == (record["rows"], record["rows"], record["positives"], 0)
        and 0 < record["positives"] < record["rows"],
        "Invalid chronology, keys or labels: " + split,
    )
    values, target = load_partition(record, plan.features)
    return LabeledMatrix(values, target), {
        "cutoff": cutoff.isoformat(),
        "label_end_exclusive": end.isoformat(),
        "latest_pair_event": actual[4].isoformat(),
        "rows": actual[0],
        "positives": actual[2],
        "temporal_or_label_violations": actual[3],
    }


def write_test_predictions(
    record: PartitionEvidence, scores: dict[str, np.ndarray], output: Path
) -> dict[str, Any]:
    """Store local test probabilities in their exact audited sample order.

    Args:
        record: File evidence for the unchanged chronological test partition.
        scores: Baseline and tuned probabilities for every test row.
        output: Project-contained new Parquet destination.

    Returns:
        File fingerprint after checking exact identity and probability read-back.
    """
    keys = pq.read_table(
        verify_registered_file(record["file"]),
        columns=["as_of_time", "user_id", "item_id", "target"],
    )
    table = keys
    for field, values in scores.items():
        require_contract(
            values.shape == (keys.num_rows,) and bool(np.isfinite(values).all()),
            "Invalid prediction row count or probability: " + field,
        )
        table = table.append_column(field, pa.array(values, type=pa.float64()))
    output = project_output_path(output)
    with output.open("xb") as stream:
        pq.write_table(table, stream, compression="zstd", row_group_size=8192)
    written = pq.read_table(output)
    require_contract(written.equals(table), "Test prediction read-back differs")
    return dict(file_record(output), rows=written.num_rows)
