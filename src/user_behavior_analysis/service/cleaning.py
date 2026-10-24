"""Orchestrate bounded parallel validation and exact disk-backed cleaning."""

import csv
import hashlib
import json
import logging
import sqlite3
import subprocess
import time
import uuid
from collections import deque
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd
import psutil
from distributed import Client
from distributed import Future

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.dao.cleaning_repository import CLEAN_EVENTS
from user_behavior_analysis.dao.cleaning_repository import CONFLICTING_KEYS
from user_behavior_analysis.dao.cleaning_repository import export_query
from user_behavior_analysis.dao.cleaning_repository import ingest_partition
from user_behavior_analysis.dao.cleaning_repository import open_cleaning_database
from user_behavior_analysis.dao.cleaning_repository import row_accounting
from user_behavior_analysis.dao.source_repository import source_declaration_status
from user_behavior_analysis.models.cleaning_models import CleaningReport
from user_behavior_analysis.models.cleaning_models import CleaningRequest
from user_behavior_analysis.models.cleaning_models import FileEvidence
from user_behavior_analysis.models.cleaning_models import MemoryEvidence
from user_behavior_analysis.models.cleaning_models import PartitionEvidence
from user_behavior_analysis.models.cleaning_models import PartitionRequest
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.models.report_models import ResourcePlan
from user_behavior_analysis.models.report_models import WorkerState
from user_behavior_analysis.service.cleaning_integrity import verify_export
from user_behavior_analysis.service.data_quality import detect_activity_anomalies
from user_behavior_analysis.service.data_quality import profile_events
from user_behavior_analysis.service.runtime import inspect_worker
from user_behavior_analysis.service.runtime import resource_plan
from user_behavior_analysis.service.runtime import start_client
from user_behavior_analysis.service.validation import normalize_partition

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RunContext:
    config: ProjectConfig
    source: Path
    request: CleaningRequest
    source_hash: str
    started: float
    plan: ResourcePlan


class _MemoryMonitor:
    def __init__(self) -> None:
        """Initialize per-run driver/worker memory and process-identity counters.

        Notes:
            Peak counters start at zero. Initial and observed worker PID sets are
            populated by sample so later observations can identify worker restarts.
        """
        self.driver_peak = 0
        self.worker_peak = 0
        self.initial_pids: set[int] = set()
        self.seen_pids: set[int] = set()

    def sample(self, client: Client | None = None) -> None:
        """Observe driver RSS and, when running, actual worker processes.

        Args:
            client: Optional live Dask client.
        """
        self.driver_peak = max(self.driver_peak, psutil.Process().memory_info().rss)
        if client is not None:
            states = cast(dict[str, WorkerState], client.run(inspect_worker))
            pids = {state["pid"] for state in states.values()}
            if not self.initial_pids:
                self.initial_pids = pids
            self.seen_pids |= pids
            self.worker_peak = max(
                self.worker_peak, *(state["rss_bytes"] for state in states.values())
            )

    def evidence(self) -> MemoryEvidence:
        """Summarize sampled resource evidence.

        Returns:
            Observed peaks and the number of newly observed worker identities.
        """
        return {
            "driver_peak_rss_bytes": self.driver_peak,
            "worker_peak_rss_bytes": self.worker_peak,
            "worker_restart_count": len(self.seen_pids - self.initial_pids),
            "sampling": (
                "Sampled at chunk/stage boundaries and every 0.25 seconds "
                + "while waiting for workers; brief peaks can be missed."
            ),
        }


def _count_structural_records(source: Path, config: ProjectConfig) -> int:
    """Scan the complete CSV for header, field-count, and quoting integrity.

    Args:
        source: Existing raw CSV, opened read-only.
        config: Expected source encoding and ordered column names.

    Returns:
        The number of CSV data records, excluding the header.

    Raises:
        ValueError: The header, CSV syntax, or a record's field count is invalid.
        OSError: The source cannot be read.

    Notes:
        Uses CSV records rather than physical lines and leaves business-value
        validation to the partition normalizer.
    """
    records = 0
    try:
        with source.open(encoding=config["data"]["encoding"], newline="") as handle:
            reader = csv.reader(handle, strict=True)
            header = next(reader, [])
            if header != config["data"]["columns"]:
                raise ValueError("CSV header differs from the source contract")
            for records, row in enumerate(reader, 1):
                if len(row) != len(config["data"]["columns"]):
                    raise ValueError(
                        f"CSV data record {records} has {len(row)} fields; expected 5"
                    )
    except csv.Error as error:
        raise ValueError(f"Malformed CSV near data record {records + 1}") from error
    return records


def _wait_partition(
    pending: deque[Future], client: Client, monitor: _MemoryMonitor
) -> PartitionEvidence:
    """Wait for the oldest pending validation while sampling process memory.

    Args:
        pending: Nonempty FIFO queue of submitted partition futures.
        client: Live Dask client used to inspect worker memory.
        monitor: Per-run memory collector updated while waiting and on completion.

    Returns:
        The completed partition's row counts and persisted output paths.

    Raises:
        IndexError: The pending queue is empty.

    Notes:
        Removes one future from the queue. Worker-task failures propagate from
        future.result rather than being converted into successful evidence.
    """
    future = pending.popleft()
    while not future.done():
        monitor.sample(client)
        time.sleep(0.25)
    result = cast(PartitionEvidence, future.result())
    monitor.sample(client)
    return result


def _validate_partitions(
    context: _RunContext, monitor: _MemoryMonitor
) -> list[PartitionEvidence]:
    """Validate every CSV chunk with bounded parallelism and source lineage.

    Args:
        context: Source, policy, destination, and effective worker resource plan.
        monitor: Collector for driver/worker RSS and worker-process identities.

    Returns:
        Partition evidence in source order for all submitted chunks.

    Raises:
        RuntimeError: A worker restarts during the run.
        ValueError: CSV parsing or partition validation fails.
        OSError: Source records or partition output files cannot be accessed.

    Notes:
        Keeps at most one pending task per planned worker, assigns stable source
        ordinals, and persists valid/rejected partitions through worker tasks.
    """
    evidence: list[PartitionEvidence] = []
    first_record = 1
    with start_client(context.config, context.plan) as client:
        monitor.sample(client)
        pending: deque[Future] = deque()
        with pd.read_csv(
            context.source,
            encoding=context.config["data"]["encoding"],
            dtype={
                column: "string[pyarrow]"
                for column in context.config["data"]["columns"]
            },
            chunksize=context.request.policy.chunk_rows,
            keep_default_na=False,
            skip_blank_lines=False,
            on_bad_lines="error",
        ) as reader:
            for partition_id, frame in enumerate(reader):
                request = PartitionRequest(
                    context.request.output_dir,
                    partition_id,
                    first_record,
                    context.request.policy,
                )
                first_record += len(frame)
                frame_future = client.scatter(frame, hash=False)
                pending.append(
                    client.submit(
                        normalize_partition, frame_future, request, pure=False
                    )
                )
                monitor.sample(client)
                if len(pending) >= context.plan["n_workers"]:
                    evidence.append(_wait_partition(pending, client, monitor))
                    LOGGER.info("Validated %s source records", first_record - 1)
        while pending:
            evidence.append(_wait_partition(pending, client, monitor))
    if monitor.evidence()["worker_restart_count"]:
        raise RuntimeError("A worker restarted; this run cannot pass resource checks")
    return evidence


def _finish(
    context: _RunContext, parts: list[PartitionEvidence], monitor: _MemoryMonitor
) -> CleaningReport:
    """Merge validated parts globally and produce complete cleaning evidence.

    Args:
        context: Run policy, source identity, output paths, and timing metadata.
        parts: Completed partition evidence in source order.
        monitor: Collector updated at merge, profile, and export boundaries.

    Returns:
        The cleaning report with row reconciliation, retained-event profile,
        anomaly diagnostics, fingerprints, resource observations, and output files.

    Raises:
        ValueError: Row accounting, retained values, source identity, or key
            integrity does not reconcile.
        OSError: Input parts or designated output artifacts cannot be accessed.

    Notes:
        Uses a temporary SQLite relation for global deduplication and exports
        clean events, conflicting keys, and separate activity diagnostics.
    """
    output = context.request.output_dir
    batch_rows = context.request.policy.export_rows
    database = PROJECT_ROOT / ".cache/cleaning" / uuid.uuid4().hex / "dedup.sqlite"
    with open_cleaning_database(database) as connection:
        for part in parts:
            ingest_partition(connection, Path(part["valid_path"]))
            monitor.sample()
            LOGGER.info("Globally merged partition %s", part["partition_id"])
        counts = row_accounting(
            connection,
            sum(part["input_rows"] for part in parts),
            sum(part["invalid_rows"] for part in parts),
        )
        LOGGER.info("Computing full-data profile")
        profile = profile_events(connection)
        monitor.sample()
        LOGGER.info("Computing exact IQR and three-sigma activity thresholds")
        anomalies = detect_activity_anomalies(
            connection, output / "activity_anomalies", batch_rows
        )
        export_query(
            connection, CONFLICTING_KEYS, output / "conflicting_keys", batch_rows
        )
        LOGGER.info("Exporting canonical clean events")
        paths = export_query(connection, CLEAN_EVENTS, output / "events", batch_rows)
        integrity = verify_export(connection, paths, batch_rows)
        monitor.sample()
    source_after = sha256_file(context.source)
    if not (
        counts["reconciled"]
        and counts["clean_rows"] > 0
        and integrity["values_match"]
        and source_after == context.source_hash
        and not profile["duplicate_keys_remaining"]
        and not profile["null_required_values"]
    ):
        raise ValueError("Full-data row accounting or integrity verification failed")
    files: list[FileEvidence] = [
        {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(output.rglob("*.parquet"))
    ]
    policy_bytes = json.dumps(asdict(context.request.policy), sort_keys=True).encode(
        "utf-8"
    )
    return {
        "status": "passed",
        "checked_at_utc": utc_timestamp(),
        "policy_version": context.request.policy.policy_version,
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "source_path": str(context.source),
        "source_size_bytes": context.source.stat().st_size,
        "source_sha256_before": context.source_hash,
        "source_sha256_after": source_after,
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
        ).strip(),
        "output_dir": str(output.relative_to(PROJECT_ROOT)),
        "row_accounting": counts,
        "profile": profile,
        "output_integrity": integrity,
        "anomalies": anomalies,
        "partitions": parts,
        "files": files,
        "resource_plan": context.plan,
        "memory": monitor.evidence(),
        "wall_seconds": round(time.perf_counter() - context.started, 4),
        "provenance_status": source_declaration_status(context.source_hash),
    }


def run_cleaning(
    config: ProjectConfig, source: Path, request: CleaningRequest
) -> CleaningReport:
    """Clean an entire CSV with bounded parallel validation and global keys.

    Args:
        config: Validated Dask resources and CSV source contract.
        source: Existing source CSV; it is opened read-only.
        request: New output location, evidence directory, and cleaning rules.

    Returns:
        Full-data quality evidence, file fingerprints, and resource observations.

    Raises:
        FileExistsError: The data output directory already exists.
        ValueError: CSV structure, reconciliation, or export checks fail.
        RuntimeError: A worker restarts during validation.

    Notes:
        Writes new local data and reports. The unique four-column key is global,
        including duplicates spanning parsing partitions. Suspect high activity
        is flagged separately rather than silently deleting valid events.
    """
    started = time.perf_counter()
    output = project_output_path(request.output_dir)
    reports = project_output_path(request.report_dir)
    if output.exists():
        raise FileExistsError(f"Refusing to replace existing cleaning output: {output}")
    request = CleaningRequest(output, reports, request.policy)
    source_hash = sha256_file(source)
    structural_count = _count_structural_records(source, config)
    context = _RunContext(
        config, source, request, source_hash, started, resource_plan(config)
    )
    output.mkdir(parents=True)
    write_json(output / "run_status.json", {"status": "running"})
    monitor = _MemoryMonitor()
    try:
        parts = _validate_partitions(context, monitor)
        if sum(part["input_rows"] for part in parts) != structural_count:
            raise ValueError("CSV parser count differs from the structural record scan")
        report = _finish(context, parts, monitor)
        write_json(reports / "quality.json", report)
        write_json(output / "run_status.json", {"status": "passed"})
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        LOGGER.exception("Cleaning failed")
        write_json(
            output / "run_status.json", {"status": "failed", "error": str(error)}
        )
        raise
    return report
