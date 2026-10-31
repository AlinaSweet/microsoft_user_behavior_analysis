"""Audit completed feature artifacts without executing a unit or integration suite."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.feature_repository import load_feature_settings
from user_behavior_analysis.models.feature_models import FeatureSettings

XML_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _require(condition: bool, message: str) -> None:
    """Stop an audit on a failed data contract.

    Args:
        condition: Actual observed contract result.
        message: Context to report when the condition fails.

    Raises:
        ValueError: A data contract failed.
    """
    if not condition:
        raise ValueError(message)


def _verify_files(rows: list[dict[str, Any]]) -> int:
    """Compare every declared artifact to its recorded SHA-256.

    Args:
        rows: File records with confined project-relative or absolute paths.

    Returns:
        Number of verified artifact records.
    """
    for row in rows:
        path = (PROJECT_ROOT / row["path"]).resolve()
        path.relative_to(PROJECT_ROOT)
        _require(sha256_file(path) == row["sha256"], "File changed: " + str(path))
    return len(rows)


def _sequence_audit(directory: Path) -> dict[str, Any]:
    """Inspect actual sequence arrays, masks and padding for a completed snapshot.

    Args:
        directory: A completed cutoff directory.

    Returns:
        Sequence dimensions, valid positions and unknown-item counts.
    """
    with np.load(directory / "sequence_tensors.npz", allow_pickle=False) as archive:
        arrays: dict[str, Any] = dict(archive)
        valid = arrays["valid_mask"]
        items = arrays["item_tokens"]
        _require(valid.shape == items.shape, "Sequence mask shape mismatch")
        _require(bool(np.all(items[~valid] == 0)), "Padding is not zero")
        _require(bool(np.all(items[valid] >= 1)), "Valid sequence token is padding")
        _require(
            bool(np.all(np.diff(valid.astype(int), axis=1) <= 0)),
            "Padding must be on the right",
        )
        _require(
            bool(np.all(arrays["raw_behavior_counts"][~valid] == 0)),
            "Padded behavior count is nonzero",
        )
        _require(
            bool(np.all(arrays["raw_behavior_counts"][valid].sum(axis=1) > 0)),
            "Valid unit has no observed behavior",
        )
        _require(bool(np.all(arrays["gap_hours"] >= 0)), "Negative sequence gap")
        _require(
            bool(np.all(~arrays["gap_defined_mask"][:, 0])),
            "First retained unit has no preceding retained gap",
        )
        _require(
            bool(np.all(arrays["gap_defined_mask"][:, 1:] == valid[:, 1:])),
            "Gap mask mismatch",
        )
        _require(
            bool(np.all(~arrays["tied_hour_mask"][~valid])),
            "Padded unit cannot be tied",
        )
        _require(len(set(arrays["user_ids"])) == len(valid), "Duplicate sequence users")
        return {
            "users": len(valid),
            "length": valid.shape[1],
            "valid_positions": int(valid.sum()),
            "unknown_item_positions": int(((items == 1) & valid).sum()),
        }


def _profile_audit(report: dict[str, Any]) -> dict[str, Any]:
    """Inspect complete stored field profiles for finite and probability ranges.

    Args:
        report: Completed snapshot with per-column full-data summaries.

    Returns:
        Checked field, proportion and constant counts.
    """
    checked_proportions = 0
    for row in report["quality"]:
        _require(row["invalid_values"] == 0, "Non-finite values: " + row["name"])
        _require(0 <= row["missing_rate"] <= 1, "Invalid missing rate")
        if row["zero_rate"] is not None:
            _require(0 <= row["zero_rate"] <= 1, "Invalid zero rate")
        name = row["name"]
        if "share" in name or "coverage" in name or "probability" in name:
            if row["minimum"] is not None:
                _require(row["minimum"] >= -1e-9, "Negative proportion: " + name)
                _require(row["maximum"] <= 1 + 1e-9, "Proportion above one: " + name)
                checked_proportions += 1
    return {
        "fields": len(report["quality"]),
        "proportion_fields_checked": checked_proportions,
        "constant_fields": sum(r["constant_in_snapshot"] for r in report["quality"]),
        "all_missing_fields": sum(r["all_missing"] for r in report["quality"]),
        "nonfinite_values": sum(r["invalid_values"] for r in report["quality"]),
    }


def _workbook_audit(path: Path) -> dict[str, Any]:
    """Inspect authored XLSX cached totals, rows and formula error cells.

    Args:
        path: Recalculated and rendered feature workbook.

    Returns:
        Cached totals and actual dictionary/quality row counts.
    """
    with ZipFile(path) as package:
        sheets = [
            ET.fromstring(package.read("xl/worksheets/sheet" + str(i) + ".xml"))
            for i in range(1, 5)
        ]
        values = {}
        for cell in sheets[0].findall(".//s:c", XML_NS):
            if cell.attrib.get("r") in ("B4", "E4", "H4"):
                value = cell.find("s:v", XML_NS)
                values[cell.attrib["r"]] = (
                    float(value.text)
                    if value is not None and value.text is not None
                    else None
                )
        _require(
            values == {"B4": 439.0, "E4": 6.0, "H4": 445.0},
            "Workbook cached count mismatch",
        )
        errors = sum(
            cell.attrib.get("t") == "e"
            for sheet in sheets
            for cell in sheet.findall(".//s:c", XML_NS)
        )
        _require(errors == 0, "Workbook formula error cell")
        dictionary_rows = len(sheets[1].findall(".//s:row", XML_NS)) - 4
        quality_rows = len(sheets[3].findall(".//s:row", XML_NS)) - 4
        _require(dictionary_rows == 445, "Workbook dictionary length mismatch")
        _require(quality_rows == 439, "Workbook quality length mismatch")
    return {
        "cached_totals": values,
        "formula_errors": errors,
        "dictionary_rows": dictionary_rows,
        "quality_rows": quality_rows,
    }


def _snapshot_audit(settings: FeatureSettings, anchor: str) -> dict[str, Any]:
    """Verify one actual snapshot's files, labels, profiles and encoded sequences.

    Args:
        settings: Configured project feature locations.
        anchor: Completed historical cutoff.

    Returns:
        Data audit evidence for one snapshot.
    """
    directory = settings.output_dir / "snapshots" / anchor
    report = json.loads((directory / "completion.json").read_text(encoding="utf-8"))
    _require(report["configuration"] == settings.options, "Configuration mismatch")
    files = _verify_files(report["files"])
    rows = sum(
        pq.ParquetFile(p).metadata.num_rows
        for p in (directory / "model_inputs").glob("*.parquet")
    )
    _require(rows == report["model_inputs"]["rows"], "Input rows mismatch")
    for path in (directory / "model_inputs").glob("*.parquet"):
        _require(len(pq.read_schema(path)) == 446, "Input field count mismatch")
    targets = pd.read_parquet(directory / "user_targets.parquet")
    _require(not bool(targets["user_id"].duplicated().any()), "Duplicate target key")
    if report["user_targets"]["label_available"]:
        _require(bool(targets["target"].isin([0, 1]).all()), "Invalid mature label")
    else:
        _require(bool(targets["target"].isna().all()), "Unavailable label became zero")
        _require(
            not bool(targets["target_available"].any()), "Unavailable label flagged"
        )
    _require(
        all(r["counts_match"] for r in report["controls"]["entity_controls"]),
        "Temporal count control failed",
    )
    return {
        "anchor": anchor,
        "verified_files": files,
        "model_input_rows": rows,
        "quality": _profile_audit(report),
        "sequences": _sequence_audit(directory),
        "label_available": report["user_targets"]["label_available"],
        "label_is_input": False,
    }


def main() -> int:
    """Run the feature delivery data audit and persist its actual findings.

    Returns:
        Zero after every data contract and fingerprint succeeds.
    """
    settings = load_feature_settings(Path("configs/feature_system.json"))
    base = json.loads(
        (PROJECT_ROOT / "data/catalog/base_raw_v2.json").read_text(encoding="utf-8")
    )
    verified = _verify_files(base["records"]["parts"]) + _verify_files(base["files"])
    catalog = json.loads(
        (PROJECT_ROOT / "data/catalog/features_raw_v2.json").read_text(encoding="utf-8")
    )
    latent_files = _verify_files(catalog["latent_files"])
    snapshots = [
        _snapshot_audit(settings, anchor) for anchor in settings.options["anchors"]
    ]
    source_csv = PROJECT_ROOT / "data/raw/user_behavior.csv"
    source_sha = sha256_file(source_csv)
    _require(source_sha == base["records"]["source_csv_sha256"], "Source CSV changed")
    database_sha = sha256_file(settings.source_database)
    _require(
        database_sha
        == "606f557d0739a6a35ecf96f2db22b761067a1ab6eee7bf44735c8f8ce8beccb4",
        "Previously audited source SQLite changed",
    )
    result = {
        "status": "passed",
        "audit_scope": "data artifacts, not a test suite",
        "source_csv_sha256": source_sha,
        "source_database_sha256": database_sha,
        "base_file_records_verified": verified,
        "base_rows": base["records"]["rows"],
        "base_values_match": base["records"]["values_match"],
        "user_hour_control": base["user_hour_control"],
        "snapshots": snapshots,
        "latent_files_verified": latent_files,
        "workbook": _workbook_audit(settings.report_dir / "feature_dictionary.xlsx"),
        "unit_or_integration_tests_run": False,
    }
    write_json(settings.report_dir / "delivery_audit.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
