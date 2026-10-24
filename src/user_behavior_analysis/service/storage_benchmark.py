"""Compare complete, value-equivalent CSV and Parquet decoding workloads."""

import time
from pathlib import Path

import psutil
import pyarrow as pa  # type: ignore[import-untyped]  # No Arrow stubs.
import pyarrow.csv as arrow_csv  # type: ignore[import-untyped]  # No Arrow stubs.
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # No Arrow stubs.

from user_behavior_analysis.dao.dataset_repository import EVENT_COLUMNS
from user_behavior_analysis.models.preprocessing_models import ReadTrial


def _csv_options() -> object:
    """Declare Arrow CSV types matching the canonical event columns.

    Returns:
        ConvertOptions using unsigned event/behavior values, string identifiers,
        and millisecond event timestamps.
    """
    return arrow_csv.ConvertOptions(
        column_types={
            "event_id": pa.uint64(),
            "user_id": pa.string(),
            "item_id": pa.string(),
            "category_id": pa.string(),
            "behavior_type": pa.uint8(),
            "event_time": pa.timestamp("ms"),
        }
    )


def _read_layout(name: str, paths: list[Path], batch_rows: int) -> tuple[int, int]:
    """Read one complete storage layout in bounded batches and count rows.

    Args:
        name: Layout label; clean_csv selects CSV, other labels select Parquet.
        paths: Ordered files belonging to the selected layout.
        batch_rows: Maximum Parquet batch size; CSV uses 16 MiB input blocks.

    Returns:
        The total decoded row count and sampled peak driver RSS in bytes.

    Raises:
        OSError: A layout file cannot be read.
        pa.ArrowInvalid: Stored values or a file format cannot be decoded as declared.

    Notes:
        Reads all files and canonical event columns without retaining the full
        dataset. Memory observations are samples rather than continuous peaks.
    """
    rows = 0
    peak = psutil.Process().memory_info().rss
    for path in paths:
        if name == "clean_csv":
            with arrow_csv.open_csv(
                path,
                read_options=arrow_csv.ReadOptions(block_size=16 * 1024**2),
                convert_options=_csv_options(),
            ) as reader:
                for batch in reader:
                    rows += batch.num_rows
                    peak = max(peak, psutil.Process().memory_info().rss)
        else:
            for batch in pq.ParquetFile(path).iter_batches(
                batch_size=batch_rows, columns=EVENT_COLUMNS
            ):
                rows += batch.num_rows
                peak = max(peak, psutil.Process().memory_info().rss)
    return rows, peak


def benchmark_layouts(
    source: list[Path],
    encoded: list[Path],
    repeats: int,
    batch_rows: int,
    csv_path: Path,
) -> list[ReadTrial]:
    """Alternate complete decodes using identical logical rows and fields.

    Args:
        source: Original cleaned Parquet parts.
        encoded: Value-equivalent compact Parquet parts.
        repeats: Positive number of trials for each layout.
        batch_rows: Maximum Parquet decoding batch; CSV buffers use 16 MiB.
        csv_path: CSV generated from the same canonical source events.

    Returns:
        Per-trial timings, decoded row counts, and sampled driver RSS.

    Raises:
        ValueError: Settings are not positive or decoded counts differ.

    Notes:
        Cache state is not controlled. Repetitions alternate layout order rather
        than claiming cold-cache storage throughput or an engine speed ranking.
    """
    if repeats <= 0 or batch_rows <= 0:
        raise ValueError("Read benchmark settings must be positive")
    results: list[ReadTrial] = []
    for repeat in range(repeats):
        layouts = [
            ("clean_csv", [csv_path]),
            ("source_parquet", source),
            ("encoded_parquet", encoded),
        ]
        if repeat % 2:
            layouts.reverse()
        for name, paths in layouts:
            started = time.perf_counter()
            rows, peak = _read_layout(name, paths, batch_rows)
            results.append(
                {
                    "layout": name,
                    "repeat": repeat + 1,
                    "rows": rows,
                    "seconds": round(time.perf_counter() - started, 4),
                    "observed_driver_peak_rss_bytes": peak,
                }
            )
    if len({trial["rows"] for trial in results}) != 1:
        raise ValueError("Compared storage layouts contain different row counts")
    return results
