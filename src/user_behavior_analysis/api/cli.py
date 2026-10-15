"""Expose check, benchmark, registration, and verification command interfaces."""

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.exceptions import ProjectError
from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.config import load_cleaning_policy
from user_behavior_analysis.config import load_config
from user_behavior_analysis.config import load_preprocessing_policy
from user_behavior_analysis.dao.artifact_repository import check_git_files
from user_behavior_analysis.dao.artifact_repository import register_artifact
from user_behavior_analysis.dao.artifact_repository import verify_artifact
from user_behavior_analysis.dao.report_repository import save_benchmark
from user_behavior_analysis.dao.source_repository import resolve_source
from user_behavior_analysis.models.cleaning_models import CleaningReport
from user_behavior_analysis.models.cleaning_models import CleaningRequest
from user_behavior_analysis.models.preprocessing_models import PreprocessingReport
from user_behavior_analysis.models.preprocessing_models import PreprocessingRequest
from user_behavior_analysis.models.report_models import ArtifactRequest
from user_behavior_analysis.models.report_models import BenchmarkReport
from user_behavior_analysis.models.report_models import EnvironmentReport
from user_behavior_analysis.models.report_models import GitFilesReport
from user_behavior_analysis.models.report_models import RegistrationReport
from user_behavior_analysis.models.report_models import VerificationReport
from user_behavior_analysis.service.benchmark import benchmark_source
from user_behavior_analysis.service.cleaning import run_cleaning
from user_behavior_analysis.service.environment import check_environment
from user_behavior_analysis.service.preprocessing import preprocess_dataset

CommandResult = (
    BenchmarkReport
    | EnvironmentReport
    | GitFilesReport
    | RegistrationReport
    | VerificationReport
    | CleaningReport
    | PreprocessingReport
)
LOGGER = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="环境、资源与数据产物管理")
    parser.add_argument("--config", help="YAML configuration path")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "benchmark"):
        command = commands.add_parser(name)
        command.add_argument("--data", help="Explicit source CSV path")
        command.add_argument("--output-dir", default="outputs/reports")
        if name == "benchmark":
            command.add_argument("--rows", type=int)
            command.add_argument("--repeats", type=int)
    command = commands.add_parser("register")
    command.add_argument("--path", required=True)
    command.add_argument("--name", required=True)
    command.add_argument(
        "--kind", choices=["raw", "interim", "processed"], required=True
    )
    command.add_argument("--recipe", required=True)
    command.add_argument("--share-location")
    command = commands.add_parser("verify")
    command.add_argument("--manifest", required=True)
    command.add_argument("--path", required=True)
    command = commands.add_parser("clean")
    command.add_argument("--data", help="Explicit source CSV path")
    command.add_argument("--policy", default="configs/cleaning.json")
    command.add_argument("--output-dir", default="data/interim/clean_v1")
    command.add_argument("--report-dir", default="outputs/reports/stage1_step3")
    command = commands.add_parser("preprocess")
    command.add_argument("--catalog", default="data/catalog/clean_v1.json")
    command.add_argument("--policy", default="configs/preprocessing.json")
    command.add_argument("--output-dir", default="data/processed/base_v1")
    command.add_argument("--report-dir", default="outputs/reports/stage1_step4")
    commands.add_parser("check-git")
    return parser


def _execute_artifact(arguments: argparse.Namespace) -> CommandResult:
    if arguments.command == "check-git":
        git_report = check_git_files()
        if git_report["issues"]:
            raise ValueError("; ".join(git_report["issues"]))
        return git_report
    if arguments.command == "register":
        request = ArtifactRequest(
            arguments.path,
            arguments.name,
            arguments.kind,
            arguments.recipe,
            arguments.share_location,
        )
        output, artifact = register_artifact(request)
        return {"manifest": str(output.relative_to(PROJECT_ROOT)), "artifact": artifact}
    if arguments.command == "verify":
        return verify_artifact(arguments.manifest, arguments.path)
    raise ValueError("Unsupported artifact command")


def _execute(arguments: argparse.Namespace) -> CommandResult:
    if arguments.command in {"check-git", "register", "verify"}:
        return _execute_artifact(arguments)
    if arguments.command == "preprocess":
        preprocessing_request = PreprocessingRequest(
            Path(arguments.catalog),
            Path(arguments.output_dir),
            Path(arguments.report_dir),
            load_preprocessing_policy(arguments.policy),
        )
        return preprocess_dataset(preprocessing_request)
    config = load_config(cast(str | None, arguments.config))
    source = resolve_source(config, cast(str | None, arguments.data))
    output_dir = project_output_path(cast(str, arguments.output_dir))
    if arguments.command == "clean":
        cleaning_request = CleaningRequest(
            Path(arguments.output_dir),
            Path(arguments.report_dir),
            load_cleaning_policy(arguments.policy),
        )
        return run_cleaning(config, source, cleaning_request)
    if arguments.command == "check":
        report = check_environment(config, source)
        write_json(output_dir / "environment_check.json", report)
        return report
    benchmark_report = benchmark_source(
        config, source, arguments.rows, arguments.repeats
    )
    request = ArtifactRequest(
        source, "user_behavior_raw", "raw", "User-provided unchanged CSV"
    )
    register_artifact(request)
    save_benchmark(benchmark_report, output_dir)
    return benchmark_report


def main(argv: Sequence[str] | None = None) -> int:
    """Run a validated project command and report actionable failures.

    Args:
        argv: Optional explicit command arguments, excluding the executable.

    Returns:
        Zero on success, or two for an expected project operation failure.
    """
    arguments = _parser().parse_args(argv)
    try:
        result = _execute(arguments)
    except (ValueError, RuntimeError, OSError, KeyError, ProjectError) as error:
        LOGGER.error("操作失败：%s", error)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
