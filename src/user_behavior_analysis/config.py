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


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigurationError(f"{field} must be a mapping with string keys")
    return cast(dict[str, object], value)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field} must be a nonempty string")
    return value


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigurationError(f"{field} must be a positive integer")
    return value


def _fraction(value: object, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0 < value < 1
    ):
        raise ConfigurationError(f"{field} must be numeric and between 0 and 1")
    return float(value)


def _byte_size(value: object, field: str) -> str:
    text = _text(value, field)
    try:
        size = parse_bytes(text)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{field} has an invalid byte size") from error
    if size <= 0:
        raise ConfigurationError(f"{field} must be positive")
    return text


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError(f"{field} must be a nonempty list")
    values = [_text(item, field) for item in value]
    if len(values) != len(set(values)):
        raise ConfigurationError(f"{field} must contain unique values")
    return values


def _memory_thresholds(document: dict[str, object]) -> MemoryThresholds:
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
