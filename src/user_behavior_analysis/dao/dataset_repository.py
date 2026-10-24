"""Read content-registered datasets in bounded, validated Arrow batches."""

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]  # No Arrow stubs.
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # No Arrow stubs.

from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.models.preprocessing_models import SourceDataset

EVENT_COLUMNS = [
    "event_id",
    "user_id",
    "item_id",
    "category_id",
    "behavior_type",
    "event_time",
]


def _verified_part(entry: object, directory: Path) -> tuple[Path, int]:
    """Verify one registered Parquet part before allowing it into a dataset.

    Args:
        entry: Catalog record declaring path, positive byte size, and SHA-256.
        directory: Project-confined dataset directory containing the part.

    Returns:
        The verified absolute file path and its Parquet metadata row count.

    Raises:
        ValueError: The entry, path, checksum, byte size, or ordered schema differs.
        FileNotFoundError: The registered part does not exist.
        OSError: The part cannot be read.
    """
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
        raise ValueError("Dataset part records require string paths")
    size = entry.get("size_bytes")
    digest = entry.get("sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("Dataset part sizes must be positive integers")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Dataset part SHA-256 values are invalid")
    part = project_output_path(entry["path"])
    if not part.is_relative_to(directory):
        raise ValueError("Registered part escapes its dataset directory")
    if not part.is_file():
        raise FileNotFoundError(f"Registered dataset part not found: {part}")
    if (
        part.stat().st_size != entry["size_bytes"]
        or sha256_file(part) != entry["sha256"]
    ):
        raise ValueError(f"Registered dataset part differs: {part}")
    parquet = pq.ParquetFile(part)
    if parquet.schema_arrow.names != EVENT_COLUMNS:
        raise ValueError(f"Registered dataset schema differs: {part}")
    return part, int(parquet.metadata.num_rows)


def load_dataset_catalog(path: Path | str) -> SourceDataset:
    """Validate an entire registered dataset before transformations.

    Args:
        path: Existing dataset catalog with ordered file fingerprints.

    Returns:
        Content-verified source parts and exact metadata row count.

    Raises:
        ValueError: A catalog field, file inventory, checksum, or count differs.
        FileNotFoundError: A registered source part is unavailable.
    """
    catalog_path = input_file_path(path)
    document = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Dataset catalog must be a JSON object")
    rows = document.get("row_count")
    if not isinstance(rows, int) or isinstance(rows, bool) or rows <= 0:
        raise ValueError("Dataset catalog row_count must be a positive integer")
    if not isinstance(document.get("dataset_path"), str):
        raise ValueError("Dataset path must be a string")
    entries = document.get("parts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Dataset parts must be a nonempty list")
    directory = project_output_path(document["dataset_path"])
    parts: list[Path] = []
    actual_rows = 0
    for entry in entries:
        part, part_rows = _verified_part(entry, directory)
        actual_rows += part_rows
        parts.append(part)
    if len(parts) != len(set(parts)) or set(parts) != set(directory.rglob("*.parquet")):
        raise ValueError("Dataset part inventory is duplicated or incomplete")
    if actual_rows != rows:
        raise ValueError("Dataset catalog row count differs from Parquet metadata")
    return SourceDataset(
        catalog_path, sha256_file(catalog_path), directory, parts, rows
    )


def read_event_batches(
    parts: list[Path], batch_rows: int, columns: list[str] | None = None
) -> Iterator[pd.DataFrame]:
    """Read projected Arrow batches without materializing complete files.

    Args:
        parts: Ordered registered Parquet part paths.
        batch_rows: Positive maximum batch size.
        columns: Optional projection; defaults to canonical event columns.

    Yields:
        Decoded bounded Pandas frames preserving source identifier characters.

    Raises:
        ValueError: The batch size is not positive.
    """
    if batch_rows <= 0:
        raise ValueError("Dataset batch size must be positive")
    for part in parts:
        for batch in pq.ParquetFile(part).iter_batches(
            batch_size=batch_rows, columns=columns or EVENT_COLUMNS
        ):
            yield batch.to_pandas()


def write_encoded_table(
    table: pa.Table, path: Path, row_group_rows: int, compression_level: int
) -> None:
    """Write a new project-confined Zstandard Parquet file.

    Args:
        table: Arrow table with already validated logical types.
        path: New destination file.
        row_group_rows: Maximum records per row group.
        compression_level: Zstandard level.

    Notes:
        Creates parent directories and writes the designated new file.
    """
    output = project_output_path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        output,
        compression="zstd",
        compression_level=compression_level,
        row_group_size=row_group_rows,
        use_dictionary=[
            column
            for column in ("category_id", "behavior_type", "user_id")
            if column in table.column_names
        ],
        coerce_timestamps="ms",
        allow_truncated_timestamps=False,
    )
