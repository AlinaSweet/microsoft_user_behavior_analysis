"""Publish new pair labels and prejoined model samples after full source audits."""

from pathlib import Path
from typing import Any

import duckdb

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import export_relation
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.dao.feature_repository import require_result_row
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.validation_models import ValidationSettings
from user_behavior_analysis.service.pair_targets import create_pair_targets
from user_behavior_analysis.service.wide_audit import file_record
from user_behavior_analysis.service.wide_contracts import identifier
from user_behavior_analysis.service.wide_contracts import require_contract


def _verified_inputs(
    settings: ValidationSettings,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify base events and all existing wide parts against their catalogs.

    Args:
        settings: Source and output locations.

    Returns:
        Wide catalog and unique input fingerprint records.

    Raises:
        ValueError: Catalog approval or source fingerprints are invalid.
    """
    wide = read_json_object(settings.wide_catalog)
    require_contract(wide["status"] == "passed", "Wide approval required")
    verify_registered_file(wide["audit_report"])
    base_path = PROJECT_ROOT / "data/catalog/base_raw_v2.json"
    base = read_json_object(base_path)
    inputs = [file_record(settings.wide_catalog), file_record(base_path)]
    inputs.append(wide["audit_report"])
    needed = [
        row
        for row in base["files"]
        if "/events/" in row["path"] or "/key_hour/" in row["path"]
    ]
    needed += [part for snap in wide["snapshots"] for part in snap["parts"]]
    for row in needed:
        verify_registered_file(row)
        inputs.append(row)
    return wide, inputs


def _export_samples(
    connection: duckdb.DuckDBPyConnection,
    settings: ValidationSettings,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join each existing wide part to dense targets using all three keys.

    Args:
        connection: Approved wide snapshot and checked targets.
        settings: New sample root.
        snapshot: Cutoff, source parts and exact expected columns.

    Returns:
        Fingerprinted sample parts with exact source-value and row-count checks.

    Raises:
        ValueError: Any joined value, key or row count differs.
    """
    output = []
    comparisons = " OR ".join(
        "s." + identifier(name) + " IS DISTINCT FROM w." + name
        for name in snapshot["columns"]
    )
    for index, part in enumerate(snapshot["parts"]):
        connection.read_parquet(str(PROJECT_ROOT / part["path"])).create_view(
            "wide_part", replace=True
        )
        evidence = export_relation(
            connection,
            (
                "SELECT w.*,t.target,t.target_available,t.label_sta"
                + "rt,t.label_end_exclusive "
            )
            + "FROM wide_part w LEFT JOIN targets t USING(as_of_time,user_id,item_id)",
            settings.sample_root / snapshot["anchor"] / (f"part_{index:02d}.parquet"),
            row_group_rows=8192,
        )
        connection.read_parquet(evidence["path"]).create_view(
            "sample_part", replace=True
        )
        row = require_result_row(
            connection.execute(
                "SELECT COUNT(*),COUNT(*) FILTER(WHERE "
                + comparisons
                + "),"
                + "COUNT(*) FILTER(WHERE s.target IS DISTINCT FROM t.target "
                + "OR s.target_available IS DISTINCT FROM t.target_available) "
                + (
                    "FROM sample_part s FULL JOIN wide_part w USING(as_"
                    + "of_time,user_id,item_id) "
                )
                + "LEFT JOIN targets t USING(as_of_time,user_id,item_id)"
            ).fetchone()
        )
        require_contract(
            row[0] == evidence["rows"] and not any(row[1:]),
            "Sample join changed values",
        )
        output.append(dict(file_record(Path(evidence["path"])), rows=evidence["rows"]))
    require_contract(
        sum(p["rows"] for p in output) == snapshot["rows"], "Sample rows changed"
    )
    return output


def build_samples(settings: ValidationSettings) -> dict[str, Any]:
    """Generate all dense labels and mature samples into unused version paths.

    Args:
        settings: Checked source and experiment settings.

    Returns:
        Passed source, label, alignment and sample manifest.

    Raises:
        FileExistsError: A destination already exists; history is never overwritten.
        ValueError: Inputs, split maturity or any full-data audit fails.
    """
    for path in (settings.label_root, settings.sample_root, settings.report_dir):
        require_contract(not path.exists(), "Use a new output version: " + str(path))
    wide, inputs = _verified_inputs(settings)
    settings.report_dir.mkdir(parents=True)
    write_json(
        settings.report_dir / "run_state.json",
        {"status": "started", "time": utc_timestamp()},
    )
    features = load_feature_settings(Path("configs/feature_system.json"))
    snapshots = []
    for snapshot in wide["snapshots"]:
        anchor = snapshot["anchor"]
        print("Building pair targets: " + anchor, flush=True)
        with feature_connection(features) as connection:
            connection.read_parquet(
                str(features.base_dir / "key_hour/data.parquet")
            ).create_view("all_keys")
            connection.read_parquet(
                str(features.base_dir / "events/*.parquet")
            ).create_view("raw_events")
            connection.read_parquet(
                [str(PROJECT_ROOT / p["path"]) for p in snapshot["parts"]]
            ).create_view("wide")
            record = create_pair_targets(connection, anchor)
            evidence = export_relation(
                connection,
                "SELECT * FROM targets ORDER BY user_id,item_id",
                settings.label_root / anchor / "pair_targets.parquet",
            )
            record["target_file"] = file_record(Path(evidence["path"]))
            record["sample_parts"] = (
                _export_samples(connection, settings, snapshot)
                if record["target_available"]
                else []
            )
            snapshots.append(record)
    by_anchor = {snap["anchor"]: snap for snap in snapshots}
    require_contract(
        all(
            by_anchor[a]["target_available"]
            for a in settings.options["splits"].values()
        ),
        "Immature split",
    )
    for record in inputs:
        verify_registered_file(record)
    result = {
        "status": "passed",
        "checked_at_utc": utc_timestamp(),
        "inputs": inputs,
        "snapshots": snapshots,
        "splits": settings.options["splits"],
        "definitions": wide["feature_definitions"],
        "sample_rows": sum(s["rows"] for s in snapshots if s["target_available"]),
        "policy": (
            "All valid records retained; >90 only flagged; dens"
            + "e exact-pair labels."
        ),
    }
    write_json(settings.report_dir / "samples.json", result)
    return result
