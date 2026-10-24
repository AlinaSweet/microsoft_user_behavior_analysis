"""Load and validate YAML values before constructing typed project settings."""

import json
from datetime import datetime
from pathlib import Path
from typing import cast

import yaml
from dask.utils import parse_bytes

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.exceptions import ConfigurationError
from user_behavior_analysis.common.utils import input_file_path
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.models.cleaning_models import CleaningPolicy
from user_behavior_analysis.models.config_models import BenchmarkSettings
from user_behavior_analysis.models.config_models import ClusterSettings
from user_behavior_analysis.models.config_models import MemoryThresholds
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.models.config_models import SourceSettings
from user_behavior_analysis.models.preprocessing_models import PreprocessingPolicy


def _mapping(value: object, field: str) -> dict[str, object]:
    """Require a configuration object whose keys are all strings.

    Args:
        value: Unvalidated value loaded from YAML or JSON.
        field: Field name included in validation errors.

    Returns:
        The original mapping with a narrowed dictionary type.

    Raises:
        ConfigurationError: The value is not a dictionary with string keys.
    """
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigurationError(f"{field} must be a mapping with string keys")
    return cast(dict[str, object], value)


def _text(value: object, field: str) -> str:
    """Require a nonempty configuration string without rewriting its value.

    Args:
        value: Unvalidated field value.
        field: Field name included in validation errors.

    Returns:
        The original string, preserving its surrounding whitespace.

    Raises:
        ConfigurationError: The value is not a string or contains only whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field} must be a nonempty string")
    return value


def _integer(value: object, field: str) -> int:
    """Require a positive integer while excluding Boolean values.

    Args:
        value: Unvalidated numeric configuration value.
        field: Field name included in validation errors.

    Returns:
        The original integer, which must be at least one.

    Raises:
        ConfigurationError: The value is Boolean, noninteger, zero, or negative.
    """
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigurationError(f"{field} must be a positive integer")
    return value


def _fraction(value: object, field: str) -> float:
    """Require a numeric fraction strictly between zero and one.

    Args:
        value: Unvalidated threshold or resource-budget fraction.
        field: Field name included in validation errors.

    Returns:
        The validated value represented as a float.

    Raises:
        ConfigurationError: The value is Boolean, nonnumeric, or outside (0, 1).
    """
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0 < value < 1
    ):
        raise ConfigurationError(f"{field} must be numeric and between 0 and 1")
    return float(value)


def _byte_size(value: object, field: str) -> str:
    """Validate a positive Dask-compatible byte-size expression.

    Args:
        value: Unvalidated size string, such as 64 MiB or 1 GiB.
        field: Field name included in validation errors.

    Returns:
        The original size string after checking that it parses to positive bytes.

    Raises:
        ConfigurationError: The value is not text, cannot be parsed, or is nonpositive.
    """
    text = _text(value, field)
    try:
        size = parse_bytes(text)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{field} has an invalid byte size") from error
    if size <= 0:
        raise ConfigurationError(f"{field} must be positive")
    return text


def _strings(value: object, field: str) -> list[str]:
    """Require a nonempty list of unique, nonblank strings.

    Args:
        value: Unvalidated list of column names, codes, or size expressions.
        field: Field name included in validation errors.

    Returns:
        Validated strings in their original order and spelling.

    Raises:
        ConfigurationError: The list is empty, has invalid strings, or has duplicates.
    """
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{field} must be a nonempty list")
    values = [_text(item, field) for item in value]
    if len(values) != len(set(values)):
        raise ConfigurationError(f"{field} must contain unique values")
    return values


def _memory_thresholds(document: dict[str, object]) -> MemoryThresholds:
    """Read and validate the four Dask worker memory thresholds.

    Args:
        document: Configuration object containing distributed.worker.memory.

    Returns:
        Target, spill, pause, and terminate fractions in strictly increasing order.

    Raises:
        ConfigurationError: A nested mapping, fraction, or threshold ordering
            is invalid.
    """
    distributed = _mapping(document.get("distributed"), "distributed")
    worker = _mapping(distributed.get("worker"), "distributed.worker")
    memory = _mapping(worker.get("memory"), "distributed.worker.memory")
    thresholds = MemoryThresholds(
        target=_fraction(memory.get("target"), "memory.target"),
        spill=_fraction(memory.get("spill"), "memory.spill"),
        pause=_fraction(memory.get("pause"), "memory.pause"),
        terminate=_fraction(memory.get("terminate"), "memory.terminate"),
    )
    values = [
        thresholds["target"],
        thresholds["spill"],
        thresholds["pause"],
        thresholds["terminate"],
    ]
    if values != sorted(set(values)):
        raise ConfigurationError("Dask memory thresholds must be strictly increasing")
    return thresholds


def _cluster_settings(value: object) -> ClusterSettings:
    """Validate local worker settings and confine their scratch directory.

    Args:
        value: Unvalidated local_cluster configuration object.

    Returns:
        Typed worker counts, byte-size settings, budget fraction, and a
        project-relative scratch directory.

    Raises:
        ConfigurationError: A required value is invalid or the worker memory limit
            is below the configured minimum.
        ValueError: The scratch directory resolves outside the project root.
    """
    local = _mapping(value, "local_cluster")
    directory = _text(local.get("local_directory"), "local_directory")
    project_output_path(directory)
    settings = ClusterSettings(
        n_workers=_integer(local.get("n_workers"), "n_workers"),
        threads_per_worker=_integer(local.get("threads_per_worker"), "threads"),
        memory_limit=_byte_size(local.get("memory_limit"), "memory_limit"),
        csv_blocksize=_byte_size(local.get("csv_blocksize"), "csv_blocksize"),
        available_memory_fraction=_fraction(
            local.get("available_memory_fraction"), "available_memory_fraction"
        ),
        minimum_worker_memory=_byte_size(
            local.get("minimum_worker_memory"), "minimum_worker_memory"
        ),
        local_directory=str(project_output_path(directory).relative_to(PROJECT_ROOT)),
    )
    if parse_bytes(settings["memory_limit"]) < parse_bytes(
        settings["minimum_worker_memory"]
    ):
        raise ConfigurationError("memory_limit must meet minimum_worker_memory")
    return settings


def _source_settings(value: object) -> SourceSettings:
    """Validate the source path setting, text encoding, and column names.

    Args:
        value: Unvalidated data configuration object.

    Returns:
        Source settings with a recognized encoding and unique column names.

    Raises:
        ConfigurationError: A required source field or text encoding is invalid.

    Notes:
        File existence and the actual CSV header are checked when resolving data.
    """
    source = _mapping(value, "data")
    encoding = _text(source.get("encoding"), "data.encoding")
    try:
        "".encode(encoding)
    except LookupError as error:
        raise ConfigurationError(f"Unknown source encoding: {encoding}") from error
    return SourceSettings(
        default_path=_text(source.get("default_path"), "data.default_path"),
        encoding=encoding,
        columns=_strings(source.get("columns"), "data.columns"),
    )


def _benchmark_settings(value: object) -> BenchmarkSettings:
    """Validate bounded sample sizes and configured CSV block expressions.

    Args:
        value: Unvalidated benchmark configuration object.

    Returns:
        Positive sample/repeat counts and validated block-size strings.

    Raises:
        ConfigurationError: Counts, block-size expressions, or list entries are invalid.
    """
    benchmark = _mapping(value, "benchmark")
    blocks = _strings(benchmark.get("block_sizes"), "benchmark.block_sizes")
    return BenchmarkSettings(
        sample_rows=_integer(benchmark.get("sample_rows"), "benchmark.sample_rows"),
        repeats=_integer(benchmark.get("repeats"), "benchmark.repeats"),
        block_sizes=[_byte_size(block, "benchmark.block_sizes") for block in blocks],
    )


def load_config(path: Path | str | None = None) -> ProjectConfig:
    """Load YAML into validated project configuration records.

    Args:
        path: Optional absolute or project-relative configuration file.

    Returns:
        Validated worker, source, and benchmark settings.

    Raises:
        FileNotFoundError: The configuration file does not exist.
        ConfigurationError: YAML structure or a configuration value is invalid.
        ValueError: A relative input or output path escapes the project.
    """
    config_path = input_file_path(path or "configs/dask.yaml")
    try:
        with config_path.open(encoding="utf-8") as handle:
            loaded: object = yaml.safe_load(handle)
    except (yaml.YAMLError, UnicodeError) as error:
        raise ConfigurationError(
            f"Invalid YAML configuration: {config_path}"
        ) from error
    document = _mapping(loaded, "configuration")
    return ProjectConfig(
        distributed={"worker": {"memory": _memory_thresholds(document)}},
        local_cluster=_cluster_settings(document.get("local_cluster")),
        data=_source_settings(document.get("data")),
        benchmark=_benchmark_settings(document.get("benchmark")),
    )


def load_cleaning_policy(path: Path | str) -> CleaningPolicy:
    """Load explicit cleaning rules with bounded partition sizes.

    Args:
        path: Project-relative or absolute JSON policy file.

    Returns:
        Validated chunk, behavior, and source-time rules.

    Raises:
        ValueError: The JSON structure or declared cleaning policy is invalid.
    """
    document = _mapping(
        json.loads(input_file_path(path).read_text(encoding="utf-8")), "cleaning"
    )
    chunk_rows = _integer(document.get("chunk_rows"), "chunk_rows")
    export_rows = _integer(document.get("export_rows"), "export_rows")
    if max(chunk_rows, export_rows) > 500000:
        raise ValueError("Cleaning batches must not exceed 500000 records")
    maximum = _text(document.get("maximum_event_time"), "maximum_event_time")
    minimum = document.get("minimum_event_time")
    datetime.strptime(maximum, "%Y-%m-%d %H")
    if minimum is not None:
        minimum = _text(minimum, "minimum_event_time")
        datetime.strptime(minimum, "%Y-%m-%d %H")
        if minimum >= maximum:
            raise ValueError("Cleaning time boundaries must be increasing")
    behaviors = _strings(document.get("allowed_behaviors"), "allowed_behaviors")
    if set(behaviors) != {"1", "2", "3", "4"}:
        raise ValueError("Behavior rules must match the four task-defined codes")
    return CleaningPolicy(
        chunk_rows,
        export_rows,
        minimum,
        maximum,
        tuple(behaviors),
        _text(document.get("policy_version"), "policy_version"),
    )


def load_preprocessing_policy(path: Path | str) -> PreprocessingPolicy:
    """Load bounded encoding and comparison settings from JSON.

    Args:
        path: Existing preprocessing policy file.

    Returns:
        Validated storage, batching, and read-comparison settings.

    Raises:
        ValueError: Any setting violates the declared resource boundaries.
    """
    document = _mapping(
        json.loads(input_file_path(path).read_text(encoding="utf-8")),
        "preprocessing",
    )
    values = {
        name: _integer(document.get(name), name)
        for name in (
            "batch_rows",
            "row_group_rows",
            "compression_level",
            "dictionary_category_limit",
            "benchmark_repeats",
        )
    }
    if max(values["batch_rows"], values["row_group_rows"]) > 500000:
        raise ValueError("Preprocessing batches must not exceed 500000 records")
    if values["compression_level"] > 9 or values["benchmark_repeats"] > 5:
        raise ValueError("Compression or repeat settings exceed project bounds")
    if values["dictionary_category_limit"] > 100000:
        raise ValueError("Category dictionary collection is bounded at 100000")
    return PreprocessingPolicy(
        values["batch_rows"],
        values["row_group_rows"],
        values["compression_level"],
        values["dictionary_category_limit"],
        values["benchmark_repeats"],
        _text(document.get("policy_version"), "policy_version"),
    )
