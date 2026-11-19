"""Data analyst: computed statistics, trend, outliers, forecast and an Excel file with charts."""

from __future__ import annotations

import base64
import io
from datetime import date

import pytest
from httpx import AsyncClient
from openpyxl import Workbook, load_workbook

from ezo_api.analytics.stats import analyse, as_notes
from ezo_api.analytics.table import Table, parse_extracted, to_number, to_period
from ezo_api.documents.executor.child import extract
from ezo_api.documents.executor.protocol import ExtractionRequest
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

CSV = (
    "Oy;Tuman;Ish o'rinlari;Korxonalar\n"
    + "".join(
        f"2026-{m:02d}-01;{'Yunusobod' if m % 2 == 0 else 'Chilonzor'};{100 + m * 10};{5 + m}\n"
        for m in range(1, 10)
    )
    + "2026-10-01;Yunusobod;900;15\n"
).encode()


def test_cells_are_read_as_numbers_and_periods() -> None:
    assert to_number("1 234,5") == 1234.5
    assert to_number("1,234.5") == 1234.5
    assert to_number("12%") == 0.12
    assert to_number("abc") is None
    assert to_period("01.03.2026") == date(2026, 3, 1)
    assert to_period("2026-03") == date(2026, 3, 1)
    assert to_period("mart 2026") == date(2026, 3, 1)
    assert to_period("Март 2026") == date(2026, 3, 1)


def test_analysis_numbers() -> None:
    rows = [[f"2026-{m:02d}-01", "A", str(10 * m)] for m in range(1, 9)]
    analysis = analyse(Table("t", ["Oy", "Hudud", "Soni"], rows))
    [profile] = analysis.numeric
    assert (profile.total, profile.mean, profile.minimum, profile.maximum) == (360, 45, 10, 80)
    [trend] = analysis.trends
    assert trend.direction == "up" and trend.r2 == 1.0 and trend.change_pct == 700
    assert [round(v) for _, v in trend.forecast] == [90, 100, 110]
    assert trend.forecast[0][0] == date(2026, 9, 1)
    assert any("forecast" in line.lower() for line in as_notes(analysis))


def test_workbook_text_from_the_worker_becomes_tables() -> None:
    text = "Oy | Soni\n2026-01 | 5\n2026-02 | 7\n\nNomi | Narx\nnon | 4000"
    tables = parse_extracted(text, None, ["Hisobot", "Narxlar"])
    assert [t.name for t in tables] == ["Hisobot", "Narxlar"]
    assert tables[0].rows == [["2026-01", "5"], ["2026-02", "7"]]


def test_isolated_executor_extracts_xlsx() -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Hisobot"
    sheet.append(["Oy", "Soni"])
    sheet.append(["2026-01", 5])
    buffer = io.BytesIO()
    book.save(buffer)
    result = extract(
        ExtractionRequest(format="xlsx", data_base64=base64.b64encode(buffer.getvalue()).decode()),
        buffer.getvalue(),
    )
    assert "Oy | Soni" in result.text and result.sections[0].heading == "Sheet: Hisobot"


async def test_chat_analyses_an_attached_csv(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    upload = await client.post(
        "/api/knowledge/documents", files={"file": ("ish_orinlari.csv", CSV, "text/csv")}
    )
    assert upload.status_code in (200, 201), upload.text
    document = upload.json()["document"]
    fake_anthropic.reply = "Tahlil tayyor."
    events = await stream_chat(
        client,
        message="Shu jadvalni tahlil qil, trend va prognoz chiqar",
        attachments=[document["id"]],
    )
    assert events[0][1]["agent"] == "data_analyst"
    system = fake_anthropic.requests[-1].system or ""
    assert "“Ish o'rinlari”: 10 values (missing 0); sum 2250" in system
    assert "Unusual value: “Ish o'rinlari” data row 10 = 900" in system
    assert "Trend of “Korxonalar” over 10 periods" in system
    assert "Linear forecast for “Korxonalar”" in system
    assert "by “Tuman”" in system
    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    data = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).content
    book = load_workbook(io.BytesIO(data))
    assert {"Ma'lumot", "Statistika", "Trend 1", "Guruh 1"} <= set(book.sheetnames)
    assert book["Trend 1"]._charts and book["Guruh 1"]._charts


async def test_chat_analyses_an_uploaded_xlsx_from_extracted_text(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Daromad"
    sheet.append(["Oy", "Daromad"])
    for m in range(1, 8):
        sheet.append([f"2026-{m:02d}", 1000 * m])
    buffer = io.BytesIO()
    book.save(buffer)
    upload = await client.post(
        "/api/knowledge/documents", files={"file": ("daromad.xlsx", buffer.getvalue())}
    )
    document = upload.json()["document"]
    fake_anthropic.reply = "Tahlil."
    events = await stream_chat(
        client, message="Excel faylni tahlil qil", attachments=[document["id"]]
    )
    assert events[0][1]["agent"] == "data_analyst"
    system = fake_anthropic.requests[-1].system or ""
    assert "“Daromad”: 7 values (missing 0); sum 28000" in system
    assert "Linear forecast for “Daromad”" in system


async def test_without_a_file_it_asks_for_one(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Fayl yuboring."
    events = await stream_chat(client, message="Excel jadvalni tahlil qil")
    # No spreadsheet was ever uploaded, so it is not the data analyst's turn.
    assert events[0][1]["agent"] != "data_analyst"


async def test_sheet_ops_without_native_parsing_use_the_extracted_table(
    client: AsyncClient, fake_anthropic: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ezo_api.agents.convert_office as office

    monkeypatch.setattr(office, "native_execution_allowed", lambda: False)
    upload = await client.post(
        "/api/knowledge/documents", files={"file": ("ish_orinlari.csv", CSV, "text/csv")}
    )
    document = upload.json()["document"]
    fake_anthropic.reply = "Saralandi."
    events = await stream_chat(
        client,
        message="Shu jadvalni Korxonalar bo'yicha kamayish tartibida sarala",
        attachments=[document["id"]],
    )
    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    data = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).content
    sheet = load_workbook(io.BytesIO(data)).active
    values = [row[3] for row in sheet.iter_rows(min_row=2, values_only=True)]
    assert values == sorted(values, reverse=True) and values[0] == 15
