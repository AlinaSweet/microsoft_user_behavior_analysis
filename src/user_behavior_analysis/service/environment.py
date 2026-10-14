"""Verify actual environment behavior and collect runtime version evidence."""

import sys
from importlib import metadata
from pathlib import Path
from typing import cast

import dask.dataframe as dd
import pandas as pd
from dask.utils import parse_bytes

from user_behavior_analysis.common.utils import utc_timestamp
from user_behavior_analysis.dao.artifact_repository import check_git_files
from user_behavior_analysis.models.config_models import ProjectConfig
from user_behavior_analysis.models.report_models import EnvironmentReport
from user_behavior_analysis.models.report_models import WorkerState
from user_behavior_analysis.service.runtime import inspect_worker
from user_behavior_analysis.service.runtime import resource_plan
from user_behavior_analysis.service.runtime import start_client


def package_versions() -> dict[str, str]:
    """Read the installed runtime package versions.

    Returns:
        Package distribution names mapped to their exact installed versions.
    """
    return {
        name: metadata.version(name)
        for name in (
            "pandas",
            "numpy",
            "dask",
            "distributed",
            "pyarrow",
            "psutil",
            "PyYAML",
        )
    }


def check_environment(config: ProjectConfig, source: Path) -> EnvironmentReport:
    """Verify live workers and a bounded source sample.

    Args:
        config: Validated project configuration.
        source: Existing CSV with the declared source schema.

    Returns:
        Structured environment evidence, without overwriting existing reports.

    Raises:
        RuntimeError: Worker properties or tracked files violate the contract.

    Notes:
        Starts local worker processes and creates managed project-local cache.
    """
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Project requires Python 3.12")
    plan = resource_plan(config)
    with start_client(config, plan) as client:
        workers = cast(dict[str, WorkerState], client.run(inspect_worker))
        if (
            len(workers) != plan["n_workers"]
            or len({state["pid"] for state in workers.values()}) != plan["n_workers"]
        ):
            raise RuntimeError("Worker process count differs from the resource plan")
        for state in workers.values():
            if state["threads"] != plan["threads_per_worker"]:
                raise RuntimeError("Worker thread count differs from the resource plan")
            if state["thresholds"] != config["distributed"]["worker"]["memory"]:
                raise RuntimeError("Worker memory thresholds were not applied")
            if state["memory_limit_bytes"] != plan["memory_limit_bytes"]:
                raise RuntimeError("Worker memory limit differs from the resource plan")
        frame = dd.read_csv(
            str(source),
            blocksize=parse_bytes(config["local_cluster"]["csv_blocksize"]),
            encoding=config["data"]["encoding"],
            dtype={column: "string[pyarrow]" for column in config["data"]["columns"]},
        )
        partition_count = frame.npartitions
        sample = cast(
            pd.DataFrame,
            client.compute(frame.head(1000, npartitions=1, compute=False)).result(
                timeout=90
            ),
        )
        if sample.columns.tolist() != config["data"]["columns"]:
            raise RuntimeError("Sample column check failed")
    git_files = check_git_files()
    if git_files["issues"]:
        raise RuntimeError("; ".join(git_files["issues"]))
    report: EnvironmentReport = {
        "status": "passed",
        "checked_at_utc": utc_timestamp(),
        "python": sys.version.split()[0],
        "packages": package_versions(),
        "sample_rows": len(sample),
        "columns": sample.columns.tolist(),
        "applied_csv_blocksize": config["local_cluster"]["csv_blocksize"],
        "csv_partition_count": partition_count,
        "source_size_bytes": source.stat().st_size,
        "source_is_local_symlink": source.is_symlink(),
        "resource_plan": plan,
        "actual_workers": workers,
        "git_files": git_files,
    }
    return report
