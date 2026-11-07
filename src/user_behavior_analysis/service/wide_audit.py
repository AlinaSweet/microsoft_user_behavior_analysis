"""Register existing prejoined snapshots only after exact full-data verification."""

from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import feature_connection
from user_behavior_analysis.dao.wide_repository import read_json_object
from user_behavior_analysis.dao.wide_repository import verify_registered_file
from user_behavior_analysis.models.feature_models import FeatureSettings
from user_behavior_analysis.service.wide_contracts import MANAGEMENT
from user_behavior_analysis.service.wide_contracts import SOURCE_KEYS
from user_behavior_analysis.service.wide_contracts import WIDE_KEYS
from user_behavior_analysis.service.wide_contracts import compare_candidate_keys
from user_behavior_analysis.service.wide_contracts import compare_source
from user_behavior_analysis.service.wide_contracts import identifier
from user_behavior_analysis.service.wide_contracts import relation_contract
from user_behavior_analysis.service.wide_contracts import require_contract
from user_behavior_analysis.service.wide_profiles import latent_coverage
from user_behavior_analysis.service.wide_profiles import profile_wide


def file_record(path: Path) -> dict[str, Any]:
    """Describe one confined immutable input or published small report.

    Args:
        path: Existing project-contained artifact.

    Returns:
        Project-relative path, exact bytes and SHA-256.
    """
    path = project_output_path(path)
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _definitions(settings: FeatureSettings) -> list[dict[str, Any]]:
    """Validate the real scalar dictionary before constructing audit SQL.

    Args:
        settings: Existing feature delivery locations.

    Returns:
        Unique registered scalar definitions, excluding raw sequence arrays.

    Raises:
        ValueError: Counts, names or owners are inconsistent.
    """
    dictionary = read_json_object(settings.report_dir / "feature_dictionary.json")
    rows = [row for row in dictionary["features"] if row["table"] != "sequence"]
    names = [identifier(row["name"]) for row in rows]
    require_contract(len(set(names)) == len(names), "Duplicate scalar names")
    require_contract(
        len(rows) == dictionary["summary"]["scalar_features"], "Scalar count mismatch"
    )
    require_contract(all(row["table"] in SOURCE_KEYS for row in rows), "Unknown owner")
    require_contract(not set(names) & set(MANAGEMENT), "Scalar/identity collision")
    require_contract(not any("target" in name for name in names), "Target in features")
    return rows


def _register_snapshot(
    connection: duckdb.DuckDBPyConnection, directory: Path, expected: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fingerprint source and wide files, then register bounded read-only views.

    Args:
        connection: New in-memory analytical connection.
        directory: One existing cutoff directory.
        expected: Previously registered feature artifact records by relative path.

    Returns:
        All verified inputs and the ordered wide part records.

    Raises:
        ValueError: Any file set, fingerprint or per-part schema is inconsistent.
    """
    inputs = []
    for entity in SOURCE_KEYS:
        path = directory / (entity + "_features.parquet")
        record = expected[str(path.relative_to(PROJECT_ROOT))]
        connection.read_parquet(str(verify_registered_file(record))).create_view(
            "source_" + entity
        )
        inputs.append(record)
    paths = sorted((directory / "model_inputs").glob("*.parquet"))
    registered = sorted(
        key
        for key in expected
        if key.startswith(str(directory.relative_to(PROJECT_ROOT)) + "/model_inputs/")
    )
    require_contract(
        [str(path.relative_to(PROJECT_ROOT)) for path in paths] == registered,
        "Wide file inventory differs from source catalog",
    )
    require_contract(bool(paths), "No wide parts")
    first_schema = pq.ParquetFile(paths[0]).schema_arrow
    parts = []
    for path in paths:
        record = expected[str(path.relative_to(PROJECT_ROOT))]
        verify_registered_file(record)
        require_contract(
            pq.ParquetFile(path).schema_arrow.equals(first_schema),
            "Part schema mismatch",
        )
        parts.append(record)
    connection.read_parquet([str(path) for path in paths]).create_view("wide")
    return inputs + parts, parts


def _snapshot_audit(
    settings: FeatureSettings,
    anchor: str,
    definitions: list[dict[str, Any]],
    expected: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify all keys, source joins and scalar values for a complete cutoff.

    Args:
        settings: Configured locations and bounded memory parameters.
        anchor: Expected cutoff date.
        definitions: All scalar fields and their producer entities.
        expected: Registered source artifact fingerprints.

    Returns:
        Snapshot audit and candidate-weighted field profiles.

    Raises:
        ValueError: Any full-data contract fails.
    """
    directory = settings.output_dir / "snapshots" / anchor
    with feature_connection(settings) as connection:
        inputs, parts = _register_snapshot(connection, directory, expected)
        columns = connection.table("wide").columns
        require_contract(
            set(columns) == set(MANAGEMENT + [row["name"] for row in definitions]),
            "Missing or unexpected wide columns",
        )
        grain = relation_contract(
            connection, "wide", WIDE_KEYS + ["category_id"], anchor
        )
        # Item determines category; a category cannot create another candidate.
        relation_contract(connection, "wide", WIDE_KEYS, anchor)
        sources = {}
        for entity, keys in SOURCE_KEYS.items():
            print(anchor + " source " + entity, flush=True)
            source_grain = relation_contract(
                connection, "source_" + entity, keys, anchor
            )
            fields = [row["name"] for row in definitions if row["table"] == entity]
            joined = compare_source(connection, entity, fields)
            require_contract(
                joined["joined_rows"] == grain["rows"], "Join multiplied rows"
            )
            sources[entity] = {"keys": keys, **source_grain, **joined}
        item_conflicts = connection.execute(
            "SELECT COUNT(*) FROM(SELECT item_id FROM source_item GROUP BY item_id "
            + "HAVING COUNT(DISTINCT category_id)>1)"
        ).fetchone()
        require_contract(
            item_conflicts is not None and item_conflicts[0] == 0,
            "Item category conflict",
        )
        key_sets = compare_candidate_keys(connection)
        profiles = [
            {"anchor": anchor, **row} for row in profile_wide(connection, definitions)
        ]
        result = {
            "anchor": anchor,
            "rows": grain["rows"],
            "columns": columns,
            "scalar_features": len(definitions),
            "grain": grain,
            "key_sets": key_sets,
            "sources": sources,
            "latent_coverage": latent_coverage(connection),
            "parts": parts,
            "inputs": inputs,
        }
    for record in inputs:
        verify_registered_file(record)
    return result, profiles


def audit_prejoined_features(
    settings: FeatureSettings, report_dir: Path, catalog_path: Path
) -> dict[str, Any]:
    """Publish a reusable wide catalog only after all configured cutoffs pass.

    Args:
        settings: Existing complete-record feature settings.
        report_dir: New directory preserving this independent audit run.
        catalog_path: New project-confined catalog path; never overwrite.

    Returns:
        Passed audit report, also persisted with field and input evidence.

    Raises:
        FileExistsError: A destination already exists.
        ValueError: Any dictionary, schema, value, key or temporal check fails.

    Notes:
        Reads and reuses existing Parquet. A failed run retains its error report
        and never publishes a passed catalog or rewrites source data.
    """
    report_dir = project_output_path(report_dir)
    catalog_path = project_output_path(catalog_path)
    if report_dir.exists() or catalog_path.exists():
        raise FileExistsError("Use new report and catalog destinations")
    report_dir.mkdir(parents=True)
    report: dict[str, Any] = {
        "status": "running",
        "started_at_utc": utc_timestamp(),
        "snapshots": [],
    }
    try:
        definitions = _definitions(settings)
        source_catalog = file_record(PROJECT_ROOT / "data/catalog/features_raw_v2.json")
        original = read_json_object(project_output_path(source_catalog["path"]))
        expected = {
            row["path"]: row
            for snapshot in original["snapshots"]
            for row in snapshot["files"]
        }
        profiles = []
        for anchor in settings.options["anchors"]:
            result, fields = _snapshot_audit(settings, anchor, definitions, expected)
            report["snapshots"].append(result)
            profiles.extend(fields)
        verify_registered_file(source_catalog)
        write_json(
            report_dir / "field_profiles.json",
            {"grain": WIDE_KEYS, "profiles": profiles},
        )
        report.update(
            {
                "status": "passed",
                "checked_at_utc": utc_timestamp(),
                "source_catalog": source_catalog,
                "field_profiles": file_record(report_dir / "field_profiles.json"),
                "scalar_features": len(definitions),
                "candidate_rows": sum(row["rows"] for row in report["snapshots"]),
                "scope": "Exact keys, left joins and all scalar values; audit only.",
            }
        )
        write_json(report_dir / "audit.json", report)
        write_json(
            catalog_path,
            {
                "kind": "prejoined_candidate_features",
                "version": 1,
                "status": "passed",
                "counting_policy": "preserve_all_valid_records_flag90",
                "keys": WIDE_KEYS,
                "management_columns": MANAGEMENT,
                "feature_definitions": definitions,
                "candidate_days": settings.options["candidate_days"],
                "labels": "Excluded; user_targets describe users, not user-item pairs",
                "sequence_arrays": "Separate user_sequences and sequence_tensors files",
                "audit_report": file_record(report_dir / "audit.json"),
                "snapshots": [
                    {
                        key: row[key]
                        for key in [
                            "anchor",
                            "rows",
                            "columns",
                            "scalar_features",
                            "parts",
                        ]
                    }
                    for row in report["snapshots"]
                ],
            },
        )
    except (OSError, ValueError, KeyError, duckdb.Error) as error:
        report.update(
            {"status": "failed", "error": str(error), "checked_at_utc": utc_timestamp()}
        )
        write_json(report_dir / "audit.json", report)
        raise
    return report
