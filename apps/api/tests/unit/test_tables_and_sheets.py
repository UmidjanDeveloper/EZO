"""Table extraction (Word exact, PDF text layout, OCR layout) and spreadsheet operations."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from ezo_api.documents.ocr import TesseractOCRProvider
from ezo_api.documents.spreadsheet.ops import (
    SheetOpError,
    SheetStep,
    formula_report,
    mentioned_columns,
    parse_sheet_request,
    run_steps,
)
from ezo_api.documents.spreadsheet.writer import Sheet
from ezo_api.documents.tables import detect_tables, docx_tables, ocr_words, pdf_words, to_sheets
from ezo_api.tools.convert_tools import line_dict
from tests.docx_fixtures import rich_docx
from tests.ocr_fixtures import needs_tesseract, png
from tests.table_fixtures import ROWS, table_image, table_pdf

EXPECTED = [list(r) for r in ROWS]


def test_word_tables_are_read_exactly() -> None:
    assert [t.rows for t in docx_tables(rich_docx())] == [
        [["Tomon", "Imzo"], ["Ijarachi", "________"]]
    ]


def test_pdf_table_is_detected_from_the_text_layout() -> None:
    words, _ = pdf_words(table_pdf(), 1)
    [table] = detect_tables(words, source="pdf_text", page=1)
    assert table.rows == EXPECTED and not table.warnings  # title and note are not part of it
    [sheet] = to_sheets([table])
    assert (
        sheet.columns == ["Viloyat", "Aholi", "O'sish %"] and sheet.rows[0][0] == "Toshkent shahri"
    )


@needs_tesseract
def test_scanned_table_is_detected_from_ocr_words() -> None:
    provider = TesseractOCRProvider.discover()
    assert provider is not None
    result = provider.extract_sync(png(table_image()), "image/png")
    lines = [line_dict(line) for line in result.pages[0].lines]
    [table] = detect_tables(ocr_words(lines), source="ocr", page=None)
    assert table.columns == 3 and len(table.rows) == 5
    assert table.rows[0] == ["Viloyat", "Aholi", "O'sish %"]
    assert table.rows[2] == ["Samarqand", "4 200 000", "1.8"]


SHEET = Sheet(
    "Data",
    ["Viloyat", "Tuman", "Aholi", "Maktablar"],
    [
        ["Toshkent", "Yunusobod", 350000, 40],
        ["Samarqand", "Urgut", 450000, 55],
        ["Toshkent", "Chilonzor", 400000, 45],
        ["Samarqand", "Urgut", 450000, 55],
        [None, None, None, None],
    ],
)


@pytest.mark.parametrize(
    ("request_text", "ops"),
    [
        ("Aholi bo'yicha kamayish tartibida sarala", ["sort"]),
        ("Dublikatlarni o'chir va bo'sh qatorlarni olib tashla", ["drop_empty", "dedupe"]),
        ("Viloyat bo'yicha guruhlab Aholi yig'indisini hisobla", ["group"]),
        ('Faqat Viloyat "Toshkent" bo\'lgan qatorlarni qoldir', ["filter"]),
        ("Отсортируй по Aholi по убыванию", ["sort"]),
        ("Group by Viloyat average Maktablar", ["group"]),
        ("Jami qator qo'sh", ["totals"]),
        ("Bu jadval nima haqida?", []),
    ],
)
def test_requests_use_real_column_names(request_text: str, ops: list[str]) -> None:
    assert [s.op for s in parse_sheet_request(request_text, SHEET.columns)] == ops


def test_operations_compute_exact_results() -> None:
    def run(text: str) -> Sheet:
        return run_steps(SHEET, parse_sheet_request(text, SHEET.columns)).sheet

    assert [r[2] for r in run("Aholi bo'yicha kamayish tartibida sarala").rows] == [
        450000,
        450000,
        400000,
        350000,
        None,
    ]
    assert len(run("Dublikatlarni o'chir va bo'sh qatorlarni olib tashla").rows) == 3
    grouped = run("Viloyat bo'yicha guruhlab Aholi yig'indisini hisobla")
    assert grouped.columns == ["Viloyat", "Aholi (sum)"]
    assert grouped.rows[:2] == [["Toshkent", 750000], ["Samarqand", 900000]]
    assert [r[1] for r in run('Faqat Viloyat "Toshkent" bo\'lgan qatorlarni qoldir').rows] == [
        "Yunusobod",
        "Chilonzor",
    ]
    assert len(run("Aholi > 380000 bo'lgan qatorlarni qoldir").rows) == 3
    totals = run_steps(SHEET, [SheetStep("totals")])
    assert totals.sheet.rows[-1] == ["Jami / Total", "", 1650000, 195]
    assert SHEET.rows[0][2] == 350000  # the input is not modified
    mean = run("Group by Viloyat average Maktablar")
    assert mean.rows[0] == ["Toshkent", 42.5]


def test_unknown_columns_are_refused() -> None:
    assert mentioned_columns("Narx bo'yicha sarala", SHEET.columns) == []
    with pytest.raises(SheetOpError, match="does not exist"):
        run_steps(SHEET, [SheetStep("sort", column="Narx")])


def test_formulas_without_saved_results_are_reported_not_calculated() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["a", "b", "sum"])
    sheet.append([1, 2, "=A2+B2"])
    buffer = io.BytesIO()
    workbook.save(buffer)  # openpyxl saves formulas without a calculated result
    report = formula_report(buffer.getvalue(), "f.xlsx")
    assert report == {"formulas": 1, "without_saved_result": 1, "examples": ["Sheet!C2"]}
