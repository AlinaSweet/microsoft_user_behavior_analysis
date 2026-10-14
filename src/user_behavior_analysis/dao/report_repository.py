"""Save structured benchmark evidence without mixing it with measurements."""

from pathlib import Path

from user_behavior_analysis.common.utils import project_output_path
from user_behavior_analysis.common.utils import write_json
from user_behavior_analysis.models.report_models import BenchmarkReport


def save_benchmark(report: BenchmarkReport, directory: Path) -> None:
    """Persist JSON measurements and a compact readable comparison.

    Args:
        report: Completed bounded benchmark evidence.
        directory: Project-confined result directory.

    Notes:
        Creates the directory and replaces its named benchmark reports.
    """
    output = project_output_path(directory)
    write_json(output / "engineering_benchmark.json", report)
    lines = [
        "# 工程资源样本验证",
        "",
        f"每次返回 {report['sample_rows']:,} 行，每种分块重复 {report['repeats']} 次。",
        "本报告只衡量首个分区的样本读取，RSS 采样可能漏掉瞬时峰值。",
        "",
        "| 分块 | 耗时中位数（秒） | worker 内存观测峰值（MiB） |",
        "|---|---:|---:|",
    ]
    for summary in report["summary"]:
        memory_mib = summary["max_observed_worker_rss_bytes"] / 2**20
        row = f"| {summary['block_size']} | {summary['median_wall_seconds']:.4f}"
        lines.append(row + f" | {memory_mib:.1f} |")
    (output / "engineering_benchmark.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
