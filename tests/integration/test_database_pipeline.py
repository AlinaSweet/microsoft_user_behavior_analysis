"""Verify complete normalized import and all SQL exports against known outcomes."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from user_behavior_analysis.api.cli import main
from user_behavior_analysis.common.constants import PROJECT_ROOT
from user_behavior_analysis.common.utils import sha256_file
from user_behavior_analysis.service.database_audit import audit_database_values
from user_behavior_analysis.service.database_audit import audit_query_exports


class DatabasePipelineTests(unittest.TestCase):
    """Exercise the public database and analysis commands with censoring and ties."""

    def test_complete_database_and_sql_workflow(self) -> None:
        """Verify cross-part import, strict funnel, repeat days and hourly ambiguity."""
        # Arrange
        scratch = PROJECT_ROOT / ".cache/tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            records = [
                (1, "001", "01", "03", 1, "2025-11-01 00"),
                (2, "001", "01", "03", 3, "2025-11-01 01"),
                (3, "001", "01", "03", 2, "2025-11-01 02"),
                (4, "001", "01", "03", 4, "2025-11-01 03"),
                (5, "001", "01", "03", 4, "2025-11-02 04"),
                (6, "002", "02", "04", 1, "2025-11-28 00"),
                (7, "003", "03", "03", 1, "2025-11-01 00"),
                (8, "003", "03", "03", 3, "2025-11-01 00"),
                (9, "003", "03", "03", 2, "2025-11-01 01"),
                (10, "003", "03", "03", 4, "2025-11-01 02"),
                (11, "004", "04", "05", 1, "2025-11-30 23"),
            ]
            frame = pd.DataFrame(
                records,
                columns=[
                    "event_id",
                    "user_id",
                    "item_id",
                    "category_id",
                    "behavior_type",
                    "event_time",
                ],
            )
            frame["event_time"] = pd.to_datetime(frame["event_time"])
            parts = []
            for index, subset in enumerate((frame.iloc[:4], frame.iloc[4:])):
                path = source / f"part_{index}.parquet"
                subset.to_parquet(path, index=False)
                parts.append(
                    {
                        "path": str(path.relative_to(PROJECT_ROOT)),
                        "size_bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
            catalog = root / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "dataset_path": str(source.relative_to(PROJECT_ROOT)),
                        "row_count": len(frame),
                        "parts": parts,
                    }
                ),
                encoding="utf-8",
            )
            database_report = root / "reports/database.json"
            output = root / "queries"
            # Act
            with redirect_stdout(io.StringIO()):
                build_status = main(
                    [
                        "build-db",
                        "--catalog",
                        str(catalog),
                        "--database",
                        str(root / "events.sqlite"),
                        "--report-dir",
                        str(root / "reports"),
                        "--batch-rows",
                        "2",
                    ]
                )
                analysis_status = main(
                    [
                        "analyze-db",
                        "--database-report",
                        str(database_report),
                        "--output-dir",
                        str(output),
                        "--report-dir",
                        str(root / "reports"),
                        "--chunk-rows",
                        "2",
                    ]
                )
            build = json.loads(database_report.read_text(encoding="utf-8"))
            analysis = json.loads(
                (root / "reports/analysis.json").read_text(encoding="utf-8")
            )
            funnel = pd.read_parquet(output / "strict_funnel").iloc[0]
            sequences = pd.read_parquet(output / "user_sequences")
            repeats = pd.read_parquet(output / "item_repurchase").set_index("item_id")
            native_audit = audit_database_values(catalog, root / "events.sqlite", 2)
            export_audits = audit_query_exports(root / "events.sqlite", analysis)
            # Assert
            self.assertEqual(native_audit["status"], "passed")
            self.assertTrue(all(item["status"] == "passed" for item in export_audits))
            self.assertEqual((build_status, analysis_status), (0, 0))
            self.assertEqual(build["loaded_rows"], 11)
            self.assertEqual(build["counts"]["users"], 4)
            self.assertEqual(build["counts"]["items"], 4)
            self.assertEqual(build["counts"]["categories"], 3)
            self.assertEqual(
                build["source_value_sha256"], build["database_value_sha256"]
            )
            self.assertTrue(all(analysis["checks"].values()))
            self.assertEqual(funnel["observed_view_pairs"], 4)
            self.assertEqual(funnel["eligible_view_pairs"], 2)
            self.assertEqual(funnel["right_censored_pairs"], 2)
            self.assertEqual(funnel["cart_pairs"], 1)
            self.assertEqual(funnel["favorite_pairs"], 1)
            self.assertEqual(funnel["purchase_pairs"], 1)
            self.assertEqual(repeats.loc["01", "repeat_buyers"], 1)
            self.assertEqual(repeats.loc["03", "repeat_buyers"], 0)
            self.assertEqual(len(sequences), 11)
            self.assertEqual(
                sequences.loc[sequences["event_id"].eq(7), "same_hour_events"].iloc[0],
                2,
            )
