"""Encode complete clean events and build three global aggregate dimensions."""

import hashlib
import json
import logging
import sqlite3
import subprocess
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import psutil
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # No Arrow stubs.

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.event_values import canonical_event_bytes
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.dataset_repository import load_dataset_catalog
from user_behavior_analysis.dao.dataset_repository import read_event_batches
from user_behavior_analysis.dao.dataset_repository import write_encoded_table
from user_behavior_analysis.dao.preprocessing_repository import export_aggregates
from user_behavior_analysis.dao.preprocessing_repository import open_aggregate_database
from user_behavior_analysis.dao.preprocessing_repository import stage_event_batch
from user_behavior_analysis.models.cleaning_models import FileEvidence
from user_behavior_analysis.models.preprocessing_models import EncodedEvents
from user_behavior_analysis.models.preprocessing_models import EncodingPlan
from user_behavior_analysis.models.preprocessing_models import PreprocessingReport
from user_behavior_analysis.models.preprocessing_models import PreprocessingRequest
from user_behavior_analysis.models.preprocessing_models import SourceDataset
from user_behavior_analysis.service.data_encoding import choose_encoding_plan
from user_behavior_analysis.service.data_encoding import encode_events
from user_behavior_analysis.service.storage_benchmark import benchmark_layouts

# PyArrow does not ship typing metadata; only its imports use targeted ignores.
LOGGER = logging.getLogger(__name__)


def _encode_and_stage(
    request: PreprocessingRequest,
    source: SourceDataset,
    plan: EncodingPlan,
    connection: sqlite3.Connection,
) -> EncodedEvents:
    """Encode every source batch and stage the same events for aggregation.

    Args:
        request: New output directory and bounded encoding/writing settings.
        source: Verified source catalog and ordered Parquet part paths.
        plan: Safe lineage width and optional complete category dictionary.
        connection: Open SQLite connection receiving canonical event values.

    Returns:
        Encoded part paths, input row count and canonical-value digest, behavior
        counts, sampled driver RSS, and the comparison CSV path.

    Raises:
        ValueError: An event cannot satisfy the canonical encoding contract.
        OSError: A source part cannot be read or an output cannot be written.
        sqlite3.DatabaseError: A canonical event batch cannot be staged.

    Notes:
        Writes compact event Parquet and benchmark_source.csv while retaining
        original logical values; output-value verification occurs after export.
    """
    input_digest = hashlib.sha256()
    paths: list[Path] = []
    rows = 0
    peak = psutil.Process().memory_info().rss
    behaviors = {code: 0 for code in ("1", "2", "3", "4")}
    csv_path = request.output_dir / "benchmark_source.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as csv_handle:
        for frame in read_event_batches(source.parts, request.policy.batch_rows):
            input_digest.update(canonical_event_bytes(frame))
            table = encode_events(frame, plan)
            path = request.output_dir / "events" / f"part_{len(paths):05d}.parquet"
            write_encoded_table(
                table,
                path,
                request.policy.row_group_rows,
                request.policy.compression_level,
            )
            frame.to_csv(
                csv_handle,
                index=False,
                header=rows == 0,
                date_format="%Y-%m-%d %H:%M:%S",
            )
            stage_event_batch(connection, frame)
            for code, count in (
                frame["behavior_type"].astype("string").value_counts().items()
            ):
                behaviors[str(code)] += int(count)
            paths.append(path)
            rows += len(frame)
            peak = max(peak, psutil.Process().memory_info().rss)
            LOGGER.info("Encoded %s complete source events", rows)
    return EncodedEvents(
        paths, rows, input_digest.hexdigest(), behaviors, peak, csv_path
    )


def _file_evidence(directory: Path) -> list[FileEvidence]:
    """Fingerprint every output Parquet part and the comparison CSV.

    Args:
        directory: Project-local preprocessing output directory.

    Returns:
        Deterministically ordered relative paths, byte sizes, and SHA-256 values.

    Raises:
        OSError: An expected output file is missing or cannot be read.
        ValueError: A recorded file path is outside the project root.
    """
    return [
        {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(
            [*directory.rglob("*.parquet"), directory / "benchmark_source.csv"]
        )
    ]


def _run(request: PreprocessingRequest, started: float) -> PreprocessingReport:
    """Execute encoding, global aggregation, value checks, and layout reads.

    Args:
        request: Verified input catalog location, new outputs, and processing policy.
        started: Run start from time.perf_counter, used for elapsed seconds.

    Returns:
        Complete preprocessing evidence including equal canonical-value hashes,
        conserved counts, file fingerprints, schemas, and read measurements.

    Raises:
        ValueError: The catalog, event values, aggregate counts, or layout counts
            fail validation, or the catalog changes during the run.
        FileNotFoundError: A required catalog or registered input part is missing.
        OSError: A source or designated output cannot be accessed.

    Notes:
        The caller prepares empty output directories. Temporary aggregation uses
        project-local SQLite storage and the raw source CSV is not rewritten.
    """
    source = load_dataset_catalog(request.source_catalog)
    plan = choose_encoding_plan(source, request.policy)
    policy = request.policy
    database = PROJECT_ROOT / ".cache/preprocessing" / uuid.uuid4().hex / "stage.sqlite"
    with open_aggregate_database(database) as connection:
        encoded = _encode_and_stage(request, source, plan, connection)
        aggregates = export_aggregates(
            connection, request.output_dir / "aggregates", policy, source.rows
        )
        if any(item["behavior_counts"] != encoded.behaviors for item in aggregates):
            raise ValueError("An aggregate does not conserve behavior counts")
    exported_rows = 0
    output_digest = hashlib.sha256()
    peak = encoded.peak_rss_bytes
    for frame in read_event_batches(encoded.paths, policy.batch_rows):
        output_digest.update(canonical_event_bytes(frame))
        exported_rows += len(frame)
        peak = max(peak, psutil.Process().memory_info().rss)
    equivalent = (
        encoded.rows == exported_rows == source.rows
        and encoded.value_sha256 == output_digest.hexdigest()
    )
    if not equivalent:
        raise ValueError("Storage encoding changed canonical event values")
    if (
        load_dataset_catalog(request.source_catalog).catalog_sha256
        != source.catalog_sha256
    ):
        raise ValueError("Source catalog changed during preprocessing")
    trials = benchmark_layouts(
        source.parts,
        encoded.paths,
        policy.benchmark_repeats,
        policy.batch_rows,
        encoded.csv_path,
    )
    peak = max(peak, *(trial["observed_driver_peak_rss_bytes"] for trial in trials))
    schema = pq.ParquetFile(encoded.paths[0]).schema_arrow
    return {
        "status": "passed",
        "checked_at_utc": utc_timestamp(),
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "source_catalog_path": str(source.catalog_path.relative_to(PROJECT_ROOT)),
        "source_catalog_sha256": source.catalog_sha256,
        "source_rows": source.rows,
        "output_rows": exported_rows,
        "input_value_sha256": encoded.value_sha256,
        "output_value_sha256": output_digest.hexdigest(),
        "values_match": equivalent,
        "policy_version": policy.policy_version,
        "policy_sha256": hashlib.sha256(
            json.dumps(asdict(policy), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "event_id_bits": plan.event_id_bits,
        "dictionary_category_count": (
            len(plan.categories) if plan.categories is not None else None
        ),
        "output_schema": {field.name: str(field.type) for field in schema},
        "aggregates": aggregates,
        "files": _file_evidence(request.output_dir),
        "read_trials": trials,
        "source_event_bytes": sum(path.stat().st_size for path in source.parts),
        "output_event_bytes": sum(path.stat().st_size for path in encoded.paths),
        "benchmark_csv_bytes": encoded.csv_path.stat().st_size,
        "observed_driver_peak_rss_bytes": peak,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
    }


def preprocess_dataset(request: PreprocessingRequest) -> PreprocessingReport:
    """Create value-equivalent compact events and user/item/time aggregates.

    Args:
        request: Verified source catalog, new data paths, and encoding policy.

    Returns:
        Full-run evidence with value hashes, aggregate totals, and read trials.

    Raises:
        FileExistsError: The requested data directory already exists.
        ValueError: Source, encoding, or count-conservation checks fail.

    Notes:
        Writes new processed data and separate reports. Existing cleaned events
        and historical benchmark reports remain inputs rather than destinations.
    """
    started = time.perf_counter()
    output = project_output_path(request.output_dir)
    reports = project_output_path(request.report_dir)
    if output.exists():
        raise FileExistsError(f"Refusing to replace processed data: {output}")
    request = PreprocessingRequest(
        request.source_catalog, output, reports, request.policy
    )
    output.mkdir(parents=True)
    write_json(output / "run_status.json", {"status": "running"})
    try:
        report = _run(request, started)
        write_json(reports / "preprocessing.json", report)
        write_json(output / "run_status.json", {"status": "passed"})
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        LOGGER.exception("Preprocessing failed")
        write_json(
            output / "run_status.json", {"status": "failed", "error": str(error)}
        )
        raise
    return report
