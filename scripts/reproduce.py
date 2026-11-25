"""Verify a clean checkout or rebuild the analysis from the registered CSV."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("data/catalog")
REBUILT = Path("outputs/reproduction")


def _python(root: Path, *arguments: str) -> None:
    """Run an existing project command through the current Python interpreter.

    Args:
        root: Checkout providing code and project-relative inputs.
        *arguments: Arguments to the interpreter.
    """
    temporary = root / ".cache/sqlite"
    temporary.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "SQLITE_TMPDIR": str(temporary),
        "MPLCONFIGDIR": str(root / ".cache/matplotlib"),
    }
    print("Running " + " ".join(arguments), flush=True)
    subprocess.run([sys.executable, *arguments], cwd=root, env=environment, check=True)


def _read(path: Path) -> dict[str, Any]:
    """Read one JSON object.

    Args:
        path: Existing project JSON file.

    Returns:
        Decoded JSON mapping.
    """
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _write(path: Path, content: dict[str, Any]) -> None:
    """Save a JSON record in the reconstruction checkout.

    Args:
        path: Destination in the isolated run.
        content: JSON-serializable mapping.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _register_cleaning(root: Path) -> None:
    """Register the regenerated historical and full-record event views.

    Args:
        root: Isolated checkout with a completed cleaning run.
    """
    evidence = "outputs/reports/stage1_step3/quality.json"
    report = _read(root / evidence)
    for name, directory, count in (
        ("clean_v1", "events", "clean_rows"),
        ("validated_records_v1", "validated", "valid_before_deduplication"),
    ):
        dataset = Path(report["output_dir"]) / directory
        parts = [
            entry for entry in report["files"] if Path(entry["path"]).parent == dataset
        ]
        _write(
            root / CATALOG / (name + ".json"),
            {
                "kind": "interim",
                "format": "parquet",
                "name": name,
                "dataset_path": dataset.as_posix(),
                "row_count": report["row_accounting"][count],
                "part_count": len(parts),
                "parts": parts,
                "quality_report": evidence,
                "source_path": "data/raw/user_behavior.csv",
                "source_sha256": report["source_sha256_after"],
            },
        )


def _model_reproduction(root: Path) -> None:
    """Recreate the feature audits, purchase labels and sample comparisons.

    Args:
        root: Isolated checkout with regenerated features.
    """
    wide = REBUILT / "wide_catalog.json"
    validation = REBUILT / "validation_config.json"
    delivery = REBUILT / "delivery_config.json"
    _python(
        root,
        "scripts/audit_wide_features.py",
        "--report-dir",
        (REBUILT / "wide").as_posix(),
        "--catalog",
        wide.as_posix(),
    )
    settings = _read(root / "configs/feature_validation.json")
    settings.update(
        wide_catalog=wide.as_posix(),
        report_dir=(REBUILT / "validation").as_posix(),
        catalog=(REBUILT / "validation_catalog.json").as_posix(),
    )
    _write(root / validation, settings)
    _python(
        root, "scripts/run_feature_validation.py", "--config", validation.as_posix()
    )
    settings = _read(root / "configs/stage2_delivery.json")
    settings.update(
        validation_config=validation.as_posix(),
        report_dir=(REBUILT / "stage2").as_posix(),
        catalog=(REBUILT / "stage2_catalog.json").as_posix(),
    )
    _write(root / delivery, settings)
    _python(root, "scripts/run_stage2_completion.py", "--config", delivery.as_posix())
    _python(
        root,
        "scripts/export_feature_dictionary.py",
        "--report-dir",
        (REBUILT / "stage2").as_posix(),
        "--output",
        (REBUILT / "stage2/feature_dictionary.xlsx").as_posix(),
    )
    sampling = REBUILT / "sampling_config.json"
    settings = _read(root / "configs/stage3_sampling.json")
    settings.update(
        validation_config=validation.as_posix(),
        report_dir=(REBUILT / "stage3_sampling").as_posix(),
        catalog=(REBUILT / "stage3_sampling_catalog.json").as_posix(),
    )
    _write(root / sampling, settings)
    _python(root, "scripts/run_stage3_sampling.py", "--config", sampling.as_posix())
    traditional = REBUILT / "traditional_config.json"
    options = _read(root / "configs/stage3_traditional.json")
    options.update(
        sampling_catalog=settings["catalog"],
        report_dir=(REBUILT / "stage3_traditional").as_posix(),
        catalog=(REBUILT / "stage3_traditional_catalog.json").as_posix(),
    )
    _write(root / traditional, options)
    _python(
        root, "scripts/run_traditional_models.py", "--config", traditional.as_posix()
    )
    _advanced_reproduction(root, settings["catalog"], options["catalog"])


def _advanced_reproduction(root: Path, sampling: str, traditional: str) -> None:
    """Build the sequence networks, stacking and explanations after 3.2.

    Args:
        root: Isolated checkout with regenerated samples and traditional models.
        sampling: Newly registered stage 3.1 catalog.
        traditional: Newly registered stage 3.2 catalog.
    """
    config = REBUILT / "advanced_config.json"
    settings = _read(root / "configs/stage3_advanced.json")
    settings.update(sampling_catalog=sampling, traditional_catalog=traditional)
    for stage in ("deep", "ensemble"):
        name = "stage3_" + stage
        settings[stage].update(
            report_dir=(REBUILT / name).as_posix(),
            catalog=(REBUILT / (name + "_catalog.json")).as_posix(),
        )
    _write(root / config, settings)
    _python(root, "scripts/run_stage3_advanced.py", "--config", config.as_posix())


def _full(csv_path: Path, destination: Path) -> None:
    """Reconstruct the analysis in a fresh copy of the committed checkout.

    Args:
        csv_path: Original CSV matching the registered source fingerprint.
        destination: New directory for the reconstructed checkout and artifacts.

    Raises:
        ValueError: The supplied CSV does not match the registered dataset.
        FileExistsError: The reconstruction destination already exists.
    """
    with csv_path.open("rb") as source:
        identity = hashlib.file_digest(source, "sha256").hexdigest()
    reference = _read(ROOT / CATALOG / "user_behavior_raw.json")
    if (
        csv_path.stat().st_size != reference["size_bytes"]
        or identity != reference["sha256"]
    ):
        raise ValueError("CSV does not match data/catalog/user_behavior_raw.json")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Choose a new reconstruction destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-tags",
            "--single-branch",
            "--no-hardlinks",
            "--",
            str(ROOT),
            str(destination),
        ],
        check=True,
    )
    print("Reconstruction checkout: " + str(destination), flush=True)
    local_csv = destination / "data/raw/user_behavior.csv"
    shutil.copyfile(csv_path, local_csv)
    with local_csv.open("rb") as copied:
        if hashlib.file_digest(copied, "sha256").hexdigest() != identity:
            raise ValueError("Source CSV changed while it was being copied")
    _python(
        destination,
        "-m",
        "user_behavior_analysis",
        "clean",
        "--data",
        local_csv.relative_to(destination).as_posix(),
    )
    _register_cleaning(destination)
    _python(destination, "-m", "user_behavior_analysis", "preprocess")
    _python(destination, "-m", "user_behavior_analysis", "database")
    _python(destination, "scripts/run_sql_analysis.py")
    _python(destination, "scripts/run_eda.py")
    (destination / CATALOG / "base_raw_v2.json").unlink()
    _python(destination, "scripts/run_features.py")
    _model_reproduction(destination)
    _python(destination, "scripts/build_dashboard_site.py")


def _verify() -> None:
    """Run quality checks, regenerate public Pages and test the Excel export."""
    _python(ROOT, "-m", "pip", "check")
    _python(ROOT, "scripts/check_quality.py", "--force")
    _python(ROOT, "scripts/build_dashboard_site.py")
    with tempfile.TemporaryDirectory(prefix="feature-dictionary-") as temporary:
        _python(
            ROOT,
            "scripts/export_feature_dictionary.py",
            "--output",
            str(Path(temporary) / "feature_dictionary.xlsx"),
        )


def main() -> int:
    """Dispatch the portable verification or source-data reconstruction.

    Returns:
        Zero after the requested workflow succeeds.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="Check a clean clone without the original CSV")
    commands.add_parser("pages", help="Rebuild the published dashboard with Python")
    full = commands.add_parser("full", help="Reconstruct from the registered raw CSV")
    full.add_argument("--csv", required=True, type=Path)
    full.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        _verify()
    elif args.command == "pages":
        _python(ROOT, "scripts/build_dashboard_site.py")
    else:
        try:
            _full(args.csv.resolve(), args.destination.resolve())
        except (OSError, ValueError) as error:
            parser.exit(2, str(error) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
