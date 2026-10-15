"""Resolve CSV locations and read samples without transforming raw values."""

import csv
import json
import os
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.models.config_models import ProjectConfig


def resolve_source(
    config: ProjectConfig,
    override: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve and validate a CSV without modifying its contents.

    Args:
        config: Validated source and resource configuration.
        override: Explicit CSV path, taking precedence over the environment.
        env: Optional environment mapping for deterministic callers and tests.

    Returns:
        A readable path with the required CSV header.

    Raises:
        FileNotFoundError: No CSV exists at the resolved path.
        ValueError: The header differs or a relative path escapes the project.
    """
    environment = os.environ if env is None else env
    source_value = (
        override
        or environment.get("USER_BEHAVIOR_CSV")
        or config["data"]["default_path"]
    )
    path = input_file_path(source_value)
    with path.open(encoding=config["data"]["encoding"], newline="") as handle:
        header = next(csv.reader(handle), [])
    expected = config["data"]["columns"]
    if header != expected:
        raise ValueError(f"CSV columns differ: expected {expected}, found {header}")
    return path


def read_sample(
    path: Path | str, rows: int, encoding: str, columns: list[str]
) -> pd.DataFrame:
    """Read bounded CSV rows with string identifiers preserved.

    Args:
        path: Existing source CSV path.
        rows: Positive maximum number of rows to return.
        encoding: Source text encoding.
        columns: Declared source columns to store as Arrow strings.

    Returns:
        A bounded DataFrame with identifiers including leading zeros.

    Raises:
        ValueError: The requested row count is not positive.
    """
    if rows <= 0:
        raise ValueError("Sample rows must be positive")
    # Keep identifiers as strings, including leading zeros; use Arrow storage.
    return pd.read_csv(
        path,
        nrows=rows,
        encoding=encoding,
        dtype={column: "string[pyarrow]" for column in columns},
    )


def source_declaration_status(source_sha256: str) -> str:
    """Read matching user-declared data-use authorization by content identity.

    Args:
        source_sha256: Fingerprint of the actual input contents.

    Returns:
        A declaration status, without certifying an external platform or license.

    Raises:
        ValueError: The local declaration file is malformed JSON.
    """
    path = PROJECT_ROOT / "data/catalog/data_provenance.json"
    if not path.exists():
        return "No matching source declaration recorded"
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Source declaration must be a JSON object")
    if document.get("source_sha256") != source_sha256:
        return "No matching source declaration recorded"
    if document.get("local_processing_authorized") is not True:
        return "Matching source declaration does not authorize local processing"
    return (
        "Matching user declaration authorizes local processing; "
        + "external platform/license not independently verified"
    )
