"""Materialize and independently check the stage-three dataset partitions."""

from datetime import datetime
from datetime import timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.dao.validation_repository import load_validation_settings
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.sampling_models import PROTOCOLS
from user_behavior_analysis.models.sampling_models import SPLITS
from user_behavior_analysis.models.sampling_models import PartitionEvidence
from user_behavior_analysis.models.sampling_models import SamplingSettings
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import identifier
from user_behavior_analysis.service.wide_contracts import require_contract

_HISTORY_FAMILIES = (
    "行为强度与偏好",
    "偏好",
    "商品生命周期与竞争",
    "严格小时漏斗",
)
_KEYS = "as_of_time,user_id,item_id"
_LABEL_FIELDS = "target,target_available,label_start,label_end_exclusive"


def load_sampling_settings(path: Path) -> SamplingSettings:
    """Resolve an approved input configuration and separate version destinations.

    Args:
        path: Project-relative or project-contained JSON configuration.

    Returns:
        Validated sampling settings.

    Raises:
        ValueError: An option or destination is invalid.
    """
    raw = read_json_object(path)
    validation = load_validation_settings(Path(raw.pop("validation_config")))
    names = ("data_root", "report_dir", "catalog")
    locations = {name: project_output_path(raw.pop(name)) for name in names}
    require_contract(
        all(
            not left.is_relative_to(right) and not right.is_relative_to(left)
            for left, right in combinations(locations.values(), 2)
        ),
        "Data, results and catalog destinations must be separate",
    )
    require_contract(
        all(location != PROJECT_ROOT for location in locations.values()),
        "Version outputs must be below the project root",
    )
    features = tuple(raw.pop("features"))
    require_contract(
        bool(features) and len(set(features)) == len(features),
        "Supply distinct continuous input names",
    )
    for name, lower, upper in (
        ("seed", 0, 2**32 - 1),
        ("negative_per_positive", 1, 100),
        ("smote_neighbors", 1, 20),
    ):
        value = raw[name]
        require_contract(
            isinstance(value, int)
            and not isinstance(value, bool)
            and lower <= value <= upper,
            f"Invalid {name}",
        )
    return SamplingSettings(
        validation=validation,
        data_root=locations["data_root"],
        report_dir=locations["report_dir"],
        catalog=locations["catalog"],
        features=features,
        seed=raw["seed"],
        negative_per_positive=raw["negative_per_positive"],
        smote_neighbors=raw["smote_neighbors"],
    )


def _view_sources(
    connection: duckdb.DuckDBPyConnection,
    settings: SamplingSettings,
    manifest: dict[str, Any],
) -> None:
    """Expose verified mature sample columns and enforce the continuous feature scope.

    Args:
        connection: Current bounded DuckDB session.
        settings: Frozen source and feature choices.
        manifest: Fingerprint-checked stage-two sample metadata.
    """
    definitions = {row["name"]: row for row in manifest["definitions"]}
    for name in settings.features:
        row = definitions.get(name, {})
        require_contract(
            row.get("family") in _HISTORY_FAMILIES
            and row.get("dtype") == "float64"
            and row.get("window_days") == 7
            and row.get("available_before_anchor") is True
            and name.endswith(("_share_7d", "_rate_7d", "_coverage_7d")),
            "Feature is outside the history-only ratio contract: " + name,
        )
    partitions = [
        str(project_output_path(part["path"]))
        for snapshot in manifest["snapshots"]
        for part in snapshot["sample_parts"]
    ]
    columns = ",".join(identifier(name) for name in settings.features)
    connection.read_parquet(partitions).project(
        _KEYS + "," + _LABEL_FIELDS + ",pair_source_max_event_time," + columns
    ).create_view("natural_samples")
    ranges = [
        f"NOT isfinite({identifier(name)}) OR {identifier(name)} NOT BETWEEN 0 AND 1"
        for name in settings.features
    ]
    out_of_range = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM natural_samples WHERE " + " OR ".join(ranges)
        ).fetchone()
    )[0]
    require_contract(out_of_range == 0, "History ratios must be within [0, 1] or null")


def _check_labels(
    connection: duckdb.DuckDBPyConnection, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    """Audit dense labels independently of partition assignment.

    Args:
        connection: Current session with the verified source samples registered.
        manifest: Approved mature and immature label snapshots.

    Returns:
        Per-cutoff sample, maturity, and alignment controls.
    """
    result = []
    for snapshot in manifest["snapshots"]:
        anchor = snapshot["anchor"]
        cutoff = datetime.fromisoformat(anchor)
        label_end = datetime.fromisoformat(snapshot["label_end_exclusive"])
        source_end = datetime.fromisoformat(snapshot["source_end_exclusive"])
        require_contract(
            label_end == cutoff + timedelta(days=7), "Invalid label window"
        )
        mature = label_end <= source_end
        path = verify_registered_file(snapshot["target_file"])
        connection.read_parquet(str(path)).create_view("approved_targets", replace=True)
        counts = require_result_row(
            connection.execute(
                "SELECT COUNT(*),COUNT(DISTINCT (user_id,item_id)),"
                + "COUNT(*) FILTER(WHERE target=1),COUNT(*) FILTER(WHERE target=0),"
                + "COUNT(*) FILTER(WHERE user_id IS NULL OR item_id IS NULL "
                + "OR user_id='' OR item_id='' OR as_of_time IS DISTINCT FROM $cutoff "
                + "OR label_start IS DISTINCT FROM $cutoff "
                + "OR label_end_exclusive IS DISTINCT FROM "
                + "($cutoff + INTERVAL '7 days') "
                + "OR target_available IS DISTINCT FROM $mature "
                + "OR CASE WHEN $mature THEN target IS NULL OR target NOT IN (0,1) "
                + "ELSE target IS NOT NULL END) FROM approved_targets",
                {"cutoff": cutoff, "mature": mature},
            ).fetchone()
        )
        require_contract(
            mature == snapshot["target_available"]
            and counts[0] == counts[1] == snapshot["rows"]
            and counts[2:4] == (snapshot["positives"], snapshot["negatives"])
            and counts[4] == 0,
            "Invalid dense label snapshot: " + anchor,
        )
        sample_rows, mismatches = require_result_row(
            connection.execute(
                "WITH s AS (SELECT * FROM natural_samples WHERE as_of_time=$cutoff),"
                + "t AS (SELECT * FROM approved_targets WHERE $mature) "
                + "SELECT COUNT(s.user_id), COUNT(*) FILTER(WHERE "
                + "s.user_id IS NULL OR t.user_id IS NULL "
                + "OR s.target IS DISTINCT FROM t.target "
                + "OR s.target_available IS DISTINCT FROM t.target_available "
                + "OR s.label_start IS DISTINCT FROM t.label_start "
                + "OR s.label_end_exclusive IS DISTINCT FROM t.label_end_exclusive "
                + "OR s.pair_source_max_event_time IS NULL "
                + "OR s.pair_source_max_event_time >= s.as_of_time) "
                + "FROM s FULL JOIN t USING ("
                + _KEYS
                + ")",
                {"cutoff": cutoff, "mature": mature},
            ).fetchone()
        )
        require_contract(
            sample_rows == (counts[0] if mature else 0) and mismatches == 0,
            "Sample alignment or past-only feature check failed: " + anchor,
        )
        result.append(
            {
                "anchor": anchor,
                "label_end_exclusive": label_end.isoformat(),
                "mature": mature,
                "candidate_rows": counts[0],
                "positive_rows": counts[2],
                "negative_rows": counts[3],
                "sample_rows": sample_rows,
                "alignment_differences": mismatches,
            }
        )
    return result


def assign_pair_groups(connection: duckdb.DuckDBPyConnection, seed: int) -> None:
    """Assign whole pairs by shuffled rank within the ever-positive group strata.

    Args:
        connection: Current session with a relation named natural_samples.
        seed: Fixed seed mixed into the pair ordering.
    """
    connection.execute(
        "CREATE TEMP TABLE pair_assignment AS WITH grouped AS ("
        + "SELECT user_id,item_id,MAX(target) AS stratum "
        + "FROM natural_samples GROUP BY user_id,item_id), ranked AS ("
        + "SELECT *,ROW_NUMBER() OVER(PARTITION BY stratum "
        + "ORDER BY md5(concat_ws('|',$seed,user_id,item_id)),"
        + "user_id,item_id) AS place,"
        + "COUNT(*) OVER(PARTITION BY stratum) AS population FROM grouped) "
        + "SELECT user_id,item_id,stratum,CASE "
        + "WHEN place<=7*population//10 THEN 'train' "
        + "WHEN place<=9*population//10 THEN 'validation' "
        + "ELSE 'test' END AS split FROM ranked",
        {"seed": str(seed)},
    )


def _write_partition(
    connection: duckdb.DuckDBPyConnection,
    protocol: str,
    split: str,
    settings: SamplingSettings,
    total: int,
) -> PartitionEvidence:
    """Write one verified partition and inspect its actual stored rows.

    Args:
        connection: Current session holding the natural samples and pair assignment.
        protocol: Time backtest or grouped random comparison.
        split: Partition within the protocol.
        settings: Destination and audited cutoff map.
        total: Full mature row count.

    Returns:
        Fingerprint and actual distribution of the written partition.
    """
    parameters: dict[str, Any]
    if protocol == "time_backtest":
        query = "SELECT s.* FROM natural_samples s WHERE as_of_time=$anchor"
        cutoff = settings.validation.options["splits"][split]
        parameters = {"anchor": datetime.fromisoformat(cutoff)}
    else:
        query = (
            "SELECT s.* FROM natural_samples s JOIN pair_assignment a "
            + "USING(user_id,item_id) WHERE a.split=$split"
        )
        parameters = {"split": split}
    path = settings.data_root / protocol / (split + ".parquet")
    stored = export_relation(
        connection, query + " ORDER BY " + _KEYS, path, parameters, row_group_rows=8192
    )
    connection.read_parquet(stored["path"]).create_view(split, replace=True)
    rows, positives, groups, positive_groups, start, end = require_result_row(
        connection.execute(
            "WITH grouped AS (SELECT user_id,item_id,COUNT(*) AS row_count,"
            + "SUM(target) AS purchases,MIN(as_of_time) AS first_anchor,"
            + "MAX(as_of_time) AS last_anchor FROM "
            + split
            + " GROUP BY user_id,item_id) "
            + "SELECT SUM(row_count),SUM(purchases), COUNT(*),"
            + "COUNT(*) FILTER(WHERE purchases>0),MIN(first_anchor),MAX(last_anchor) "
            + "FROM grouped"
        ).fetchone()
    )
    require_contract(
        rows == stored["rows"] and rows is not None and 0 < positives < rows,
        f"Both classes must be present in {protocol}/{split}",
    )
    return {
        "file": file_record(Path(stored["path"])),
        "rows": rows,
        "positives": positives,
        "negatives": rows - positives,
        "positive_rate": positives / rows,
        "row_share": rows / total,
        "pair_groups": groups,
        "positive_pair_groups": positive_groups,
        "first_anchor": start.date().isoformat(),
        "last_anchor": end.date().isoformat(),
    }


def _check_partition_union(
    connection: duckdb.DuckDBPyConnection, protocol: str, expected_rows: int
) -> dict[str, int]:
    """Check complete label conservation and cross-partition pair overlap.

    Args:
        connection: Current session with the three written partitions registered.
        protocol: Partition protocol defining whether pair overlap is allowed.
        expected_rows: Total accepted labeled rows.

    Returns:
        Actual alignment and repeated-pair counts.
    """
    union = " UNION ALL ".join(
        f"SELECT '{split}' AS dataset_split, {_KEYS}, target FROM {split}"
        for split in SPLITS
    )
    connection.execute("CREATE OR REPLACE TEMP VIEW partition_rows AS " + union)
    rows, differences = require_result_row(
        connection.execute(
            "SELECT COUNT(*),COUNT(*) FILTER(WHERE s.user_id IS NULL "
            + "OR p.user_id IS NULL OR s.target IS DISTINCT FROM p.target) "
            + "FROM natural_samples s FULL JOIN partition_rows p USING ("
            + _KEYS
            + ")"
        ).fetchone()
    )
    overlap = require_result_row(
        connection.execute(
            "SELECT COUNT(*) FROM (SELECT user_id,item_id FROM partition_rows "
            + "GROUP BY user_id,item_id HAVING COUNT(DISTINCT dataset_split)>1)"
        ).fetchone()
    )[0]
    require_contract(rows == expected_rows and differences == 0, "Split union differs")
    require_contract(
        protocol != "grouped_721" or overlap == 0, "A pair crossed grouped splits"
    )
    return {
        "labeled_rows": rows,
        "alignment_differences": differences,
        "cross_pairs": overlap,
    }


def _check_group_quotas(records: dict[str, PartitionEvidence]) -> dict[str, Any]:
    """Compare the written pair strata against the exact rounded grouping quotas.

    Args:
        records: Group and positive-group totals measured from the written splits.

    Returns:
        The realized train, validation and test pair counts by stratum.
    """
    positive = [records[split]["positive_pair_groups"] for split in SPLITS]
    negative = [
        records[split]["pair_groups"] - count for split, count in zip(SPLITS, positive)
    ]
    strata = {"ever_positive": positive, "never_positive": negative}
    for counts in strata.values():
        total = sum(counts)
        train, train_validation = 7 * total // 10, 9 * total // 10
        expected = [train, train_validation - train, total - train_validation]
        require_contract(counts == expected, "Written strata differ from 7:2:1 quotas")
    return {name: dict(zip(SPLITS, counts)) for name, counts in strata.items()}


def build_partitions(
    settings: SamplingSettings, manifest: dict[str, Any]
) -> tuple[dict[str, dict[str, PartitionEvidence]], dict[str, Any]]:
    """Generate both complete natural-distribution dataset protocols.

    Args:
        settings: Configured paths and predeclared sample parameters.
        manifest: Approved sample metadata whose input files have been verified.

    Returns:
        Registered dataset artifacts and label/split audit results.
    """
    require_contract(
        manifest["splits"] == settings.validation.options["splits"]
        and set(manifest["splits"].values())
        == {
            snap["anchor"] for snap in manifest["snapshots"] if snap["target_available"]
        },
        "The three declared time anchors must match the mature sample snapshots",
    )
    records: dict[str, dict[str, PartitionEvidence]] = {}
    controls = {}
    spill = settings.data_root / "spill"
    spill.mkdir()
    with duckdb.connect() as connection:
        connection.execute("SET threads=2")
        connection.execute("SET memory_limit='768MB'")
        connection.execute("SET temp_directory = ?", [str(spill)])
        _view_sources(connection, settings, manifest)
        labels = _check_labels(connection, manifest)
        assign_pair_groups(connection, settings.seed)
        for protocol in PROTOCOLS:
            records[protocol] = {
                split: _write_partition(
                    connection, protocol, split, settings, manifest["sample_rows"]
                )
                for split in SPLITS
            }
            controls[protocol] = _check_partition_union(
                connection, protocol, manifest["sample_rows"]
            )
    spill.rmdir()
    return records, {
        "labels": labels,
        "protocols": controls,
        "group_strata": _check_group_quotas(records["grouped_721"]),
    }


def load_partition(
    record: PartitionEvidence, features: tuple[str, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """Return verified features and labels while leaving IDs and times out of models.

    Args:
        record: Stored split fingerprint and class accounting.
        features: Frozen numeric columns in model order.

    Returns:
        A float32 feature matrix and integer binary targets.
    """
    table = pq.read_table(
        verify_registered_file(record["file"]), columns=[*features, "target"]
    )
    values = np.column_stack(
        [table[name].to_numpy().astype(np.float32, copy=False) for name in features]
    )
    target = table["target"].to_numpy().astype(np.int8, copy=False)
    require_contract(
        len(target) == record["rows"] and int(target.sum()) == record["positives"],
        "Partition class accounting differs from manifest",
    )
    return values, target
