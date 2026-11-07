"""Read registered candidate features in bounded, fingerprint-checked batches."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from typing import cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file


def read_json_object(path: Path) -> dict[str, Any]:
    """Read a confined JSON object without changing its source.

    Args:
        path: Existing project-contained JSON path.

    Returns:
        The decoded object.

    Raises:
        ValueError: The document is not an object or escapes the project.
    """
    result = json.loads(
        input_file_path(project_output_path(path)).read_text(encoding="utf-8")
    )
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return cast(dict[str, Any], result)


def verify_registered_file(record: dict[str, Any]) -> Path:
    """Check the path, byte count and SHA-256 of one registered local artifact.

    Args:
        record: Project path, byte count and SHA-256 expected by the catalog.

    Returns:
        The verified project-contained path.

    Raises:
        ValueError: A size or content fingerprint differs.
        FileNotFoundError: The artifact is unavailable on this computer.
    """
    path = input_file_path(project_output_path(record["path"]))
    if path.stat().st_size != record["bytes"] or sha256_file(path) != record["sha256"]:
        raise ValueError("Registered artifact changed: " + str(path))
    return path


def iter_wide_features(
    catalog_path: Path, anchor: str, columns: list[str], batch_size: int = 8192
) -> Iterator[pa.RecordBatch]:
    """Yield selected columns from an audited cutoff in bounded batches.

    Args:
        catalog_path: Passed prejoined-feature catalog.
        anchor: Exact registered cutoff date.
        columns: Unique identity, management or scalar names; targets are excluded.
        batch_size: Maximum rows in each Arrow batch, between 1 and 100000.

    Yields:
        Arrow record batches retaining requested column order and original nulls.

    Raises:
        ValueError: Catalog, columns, schema or fingerprints are invalid.
        FileNotFoundError: A registered report or local data part is unavailable.

    Notes:
        Verifies the report and every part before yielding. No imputation,
        feature selection, target join or train-validation split is performed.
    """
    catalog = read_json_object(catalog_path)
    if (
        catalog.get("status") != "passed"
        or catalog.get("kind") != "prejoined_candidate_features"
    ):
        raise ValueError("A passed prejoined-feature catalog is required")
    if not 1 <= batch_size <= 100000:
        raise ValueError("Batch size must be between 1 and 100000")
    snapshots = [row for row in catalog["snapshots"] if row["anchor"] == anchor]
    if len(snapshots) != 1:
        raise ValueError("Cutoff is absent or ambiguous")
    snapshot = snapshots[0]
    if (
        not columns
        or len(set(columns)) != len(columns)
        or not set(columns) <= set(snapshot["columns"])
    ):
        raise ValueError("Choose distinct registered columns; targets are excluded")
    report = read_json_object(verify_registered_file(catalog["audit_report"]))
    if report.get("status") != "passed":
        raise ValueError("Audit report did not pass")
    approved = [row for row in report["snapshots"] if row["anchor"] == anchor]
    if len(approved) != 1 or any(
        snapshot[key] != approved[0][key]
        for key in ("parts", "rows", "columns", "scalar_features")
    ):
        raise ValueError("Catalog differs from the approved audit")
    parts = [verify_registered_file(row) for row in snapshot["parts"]]
    if len(set(parts)) != len(parts):
        raise ValueError("Duplicate registered parts")
    observed = 0
    for path in parts:
        parquet = pq.ParquetFile(path)
        if parquet.schema_arrow.names != snapshot["columns"]:
            raise ValueError("Wide schema changed")
        observed += parquet.metadata.num_rows
    if observed != snapshot["rows"]:
        raise ValueError("Wide row count changed")
    for path in parts:
        yield from pq.ParquetFile(path).iter_batches(
            batch_size=batch_size, columns=columns
        )
