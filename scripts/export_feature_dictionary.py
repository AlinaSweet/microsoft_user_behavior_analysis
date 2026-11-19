"""Export the feature definitions, matrix mapping and metrics as native Excel."""

import argparse
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import cast

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import Alignment  # type: ignore[import-untyped]
from openpyxl.styles import Font  # type: ignore[import-untyped]
from openpyxl.styles import PatternFill  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from openpyxl.worksheet.table import Table  # type: ignore[import-untyped]
from openpyxl.worksheet.table import TableStyleInfo  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
CellValue = str | int | float | bool | None
DEFINITIONS = (
    ("字段名", "name"),
    ("业务含义", "chinese_name"),
    ("来源表", "table"),
    ("特征族", "family"),
    ("评估组", "current_group"),
    ("筛选状态", "current_status"),
    ("业务保护", "business_protected"),
    ("训练缺失率", "training_missing_rate"),
    ("训练互信息", "training_mi"),
    ("当前预处理", "current_preprocessing"),
    ("筛选原因", "decision_reason"),
    ("计算口径", "calculation_explanation"),
    ("适用边界", "description"),
    ("天窗口", "window_days"),
    ("类型", "dtype"),
    ("原始产物", "artifact"),
)
REPRESENTATIONS = (
    ("表示字段", "name"),
    ("业务含义", "chinese_name"),
    ("表示类别", "family"),
    ("计算方法", "calculation"),
    ("训练与推理规则", "current_preprocessing"),
    ("用途及限制", "description"),
)


@dataclass(frozen=True)
class _Sheet:
    """Describe the contents of one filterable worksheet.

    Attributes:
        name: Worksheet title.
        headers: Display headings.
        rows: Typed cell values in source order.
        formats: Number formats keyed by one-based column.
    """

    name: str
    headers: tuple[str, ...]
    rows: list[list[CellValue]]
    formats: dict[int, str]


def _mapped_rows(
    records: list[dict[str, Any]], columns: tuple[tuple[str, str], ...]
) -> list[list[CellValue]]:
    """Project JSON rows onto the worksheet's visible columns.

    Args:
        records: Source dictionaries in registered order.
        columns: Heading and source field pairs.

    Returns:
        Native typed values, with structured fields represented as JSON text.
    """
    rows = []
    for record in records:
        values = [
            (
                record.get(key) or record.get("calculation")
                if key == "calculation_explanation"
                else record.get(key)
            )
            for _, key in columns
        ]
        rows.append(
            [
                (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                )
                for value in values
            ]
        )
    return rows


def _matrix_rows(data: dict[str, Any]) -> list[list[CellValue]]:
    """Map each encoded column to its original field or calculated representation.

    Args:
        data: Current dictionary JSON including matrix column names.

    Returns:
        Matrix column mappings indexed from zero.
    """
    rows: list[list[CellValue]] = []
    for index, name in enumerate(data["matrix_column_names"]):
        field, separator, encoding = name.partition("__")
        if name.startswith("category_embedding_"):
            rows.append([index, name, "三类训练类别的联合投影", "稀疏预嵌入"])
        elif separator:
            method = "目标编码" if encoding == "te" else "独热或缺失标记"
            rows.append([index, name, field, method])
        else:
            rows.append([index, name, name, "数值标准化"])
    return rows


def _sheets(data: dict[str, Any], metrics: dict[str, Any]) -> tuple[_Sheet, ...]:
    """Prepare all four dictionary sheets.

    Args:
        data: Published or regenerated dictionary.
        metrics: Fixed experiment validation and test results.

    Returns:
        Sheet content for definitions, transformations, mapping and metrics.
    """
    validation = metrics["evaluations"]["validation"]["metrics"]["all"]
    test = metrics["evaluations"]["test"]["metrics"]["all"]
    comparison = [
        [
            name,
            row["roc_auc"],
            row["average_precision"],
            test[name]["roc_auc"],
            test[name]["average_precision"],
            "已冻结基线" if name in {"basic", "business"} else "目标编码对照",
        ]
        for name, row in validation.items()
    ]
    return (
        _Sheet(
            "特征定义与筛选",
            tuple(label for label, _ in DEFINITIONS),
            _mapped_rows(data["features"], DEFINITIONS),
            {8: "0.00%", 9: "0.000000"},
        ),
        _Sheet(
            "预处理表示",
            tuple(label for label, _ in REPRESENTATIONS),
            _mapped_rows(data["representations"], REPRESENTATIONS),
            {},
        ),
        _Sheet(
            "矩阵列映射",
            ("列索引", "矩阵列名", "源字段或输入", "表示方式"),
            _matrix_rows(data),
            {},
        ),
        _Sheet(
            "固定实验对照",
            ("输入组", "验证AUC", "验证AP", "测试AUC", "测试AP", "性质"),
            comparison,
            dict.fromkeys(range(2, 6), "0.00000"),
        ),
    )


def _add_sheet(book: Workbook, spec: _Sheet, index: int) -> None:
    """Write one native Excel table and freeze its identifying column.

    Args:
        book: New workbook.
        spec: Complete headings and tabular values.
        index: Unique identifier for the Excel table.
    """
    sheet = book.create_sheet(spec.name)
    sheet.sheet_view.showGridLines = False
    sheet.append([spec.name])
    sheet["A1"].font = Font(bold=True, color="173F52", size=15)
    sheet.append([])
    sheet.append(spec.headers)
    for row in spec.rows:
        sheet.append(row)
        for cell in sheet[sheet.max_row]:
            if cell.data_type == "f":
                cell.data_type = "s"
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if cell.column in spec.formats:
                cell.number_format = spec.formats[cell.column]
        sheet.row_dimensions[sheet.max_row].height = 38
    for number, header in enumerate(spec.headers, start=1):
        column = sheet.cell(3, number)
        column.fill = PatternFill("solid", fgColor="173F52")
        column.font = Font(color="FFFFFF", bold=True)
        column.alignment = Alignment(horizontal="center", vertical="center")
        lengths = (len(str(row[number - 1] or "")) for row in spec.rows)
        sheet.column_dimensions[get_column_letter(number)].width = min(
            45, max(13, len(header) * 2, max(lengths, default=0))
        )
    reference = f"A3:{get_column_letter(len(spec.headers))}{sheet.max_row}"
    table = Table(displayName=f"Dictionary{index}", ref=reference)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    sheet.add_table(table)
    sheet.freeze_panes = "B4"


def _read(path: Path) -> dict[str, Any]:
    """Load a UTF-8 result object.

    Args:
        path: JSON result path.

    Returns:
        Decoded result mapping.
    """
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    """Export a new workbook from the selected result directory.

    Returns:
        Zero after the workbook is saved.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir", type=Path, default=ROOT / "outputs/reports/stage2"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    book = Workbook()
    book.remove(book.active)
    data = _read(args.report_dir / "feature_dictionary.json")
    metrics = _read(args.report_dir / "encoding_experiments.json")
    for index, spec in enumerate(_sheets(data, metrics), start=1):
        _add_sheet(book, spec, index)
    payload = io.BytesIO()
    book.save(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as file:
        file.write(payload.getvalue())
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
