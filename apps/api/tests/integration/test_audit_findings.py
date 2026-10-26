"""Regressions for audit findings F19-F22 (docs/master/CLAUDE_MASTER_AUDIT.md §3).

These run with the session-wide native regression-fixture exception switched OFF,
exactly as the production API runs.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from docx import Document
from httpx import AsyncClient

from ezo_api.documents import isolation
from ezo_api.tools.base import ToolResult
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

TABLE = json.dumps(
    {
        "title": "Oylik xarajatlar",
        "sheets": [{"name": "X", "columns": ["Modda", "Summa"], "rows": [["Ijara", 4500000]]}],
    }
)
ARIZA = json.dumps(
    {
        "title": "Ariza",
        "fields": {"recipient": "Tuman hokimiga", "applicant": None, "date": None},
        "sections": [{"heading": None, "text": "Uy-joy masalasida yordam so'rayman."}],
        "missing": [],
    }
)


@pytest.fixture
def production_isolation() -> Iterator[None]:
    token = isolation._FIXTURES.set(False)
    try:
        yield
    finally:
        isolation._FIXTURES.reset(token)


async def test_f19_chat_creates_a_real_docx_in_production(
    client: AsyncClient, fake_anthropic: FakeProvider, production_isolation: None
) -> None:
    assert not isolation.native_execution_allowed()
    fake_anthropic.replies = [ARIZA, "Ariza tayyor."]
    events = await stream_chat(client, message="Hokimga rasmiy ariza yozib ber, word fayl qilib")
    message = events[-1][1]["message"]
    [artifact] = message["metadata"]["artifacts"]
    docx = await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")
    paragraphs = [p.text for p in Document(io.BytesIO(docx.content)).paragraphs]
    assert "Uy-joy masalasida yordam so'rayman." in paragraphs
    assert "Fayl yaratilmadi" not in message["content"]


async def test_f19_chat_creates_a_real_xlsx_in_production(
    client: AsyncClient, fake_anthropic: FakeProvider, production_isolation: None
) -> None:
    from openpyxl import load_workbook

    fake_anthropic.replies = [TABLE, "Jadval tayyor."]
    events = await stream_chat(client, message="Oylik xarajatlar uchun excel jadval yarat")
    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    data = await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")
    assert load_workbook(io.BytesIO(data.content)).active["B2"].value == 4500000


async def test_f19_failed_file_tool_cannot_be_reported_as_done(
    client: AsyncClient, app, fake_anthropic: FakeProvider, production_isolation: None
) -> None:
    tools = app.state.services.tools
    original = tools.execute

    async def broken(name, arguments, ctx):  # type: ignore[no-untyped-def]
        if name == "create_spreadsheet":
            return ToolResult(ok=False, summary="", error="disk full")
        return await original(name, arguments, ctx)

    tools.execute = broken
    try:
        # The model still claims success; EZO must append the fixed failure notice.
        fake_anthropic.replies = [TABLE, "Jadval tayyor."]
        events = await stream_chat(client, message="Oylik xarajatlar uchun excel jadval yarat")
    finally:
        tools.execute = original
    message = events[-1][1]["message"]
    assert message["metadata"]["artifacts"] == []
    assert "Fayl yaratilmadi (disk full)" in message["content"]


async def test_f21_spreadsheet_cells_are_typed_and_bounded(client: AsyncClient) -> None:
    ok = await client.post(
        "/api/office/spreadsheets",
        json={"title": "Hisobot", "sheets": [{"columns": ["A", "B"], "rows": [[1, "x"]]}]},
    )
    assert ok.status_code in (200, 201), ok.text
    for rows in (
        [["x" * 32_768]],  # longer than an Excel cell
        [[{"nested": "object"}]],  # not a cell value
        [[0] * 101],  # wider than 100 columns
    ):
        bad = await client.post(
            "/api/office/spreadsheets",
            json={"title": "Hisobot", "sheets": [{"columns": ["A"], "rows": rows}]},
        )
        assert bad.status_code == 422, rows
    too_many = await client.post(
        "/api/office/spreadsheets",
        json={
            "title": "Katta",
            "sheets": [{"columns": ["A"] * 20, "rows": [[1] * 20] * 10_001}],
        },
    )
    assert too_many.status_code in (413, 422)


async def test_f22_student_uploads_have_queue_and_storage_quotas(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ezo_api.student import ingestion

    monkeypatch.setattr(ingestion, "MAX_PENDING_RAW_JOBS", 2)
    for n in range(2):
        response = await client.post(
            "/api/student/uploads", params={"filename": f"b{n}.pdf"}, content=b"%PDF-" + bytes([n])
        )
        assert response.status_code == 201
    third = await client.post(
        "/api/student/uploads", params={"filename": "c.pdf"}, content=b"%PDF-c"
    )
    assert third.status_code == 429 and "at once" in third.text
    # Re-sending an existing source is idempotent, not a new queued job.
    again = await client.post(
        "/api/student/uploads", params={"filename": "b0.pdf"}, content=b"%PDF-\x00"
    )
    assert again.status_code == 201

    monkeypatch.setattr(ingestion, "MAX_PENDING_RAW_JOBS", 100)
    monkeypatch.setattr(ingestion, "MAX_RAW_BYTES_PER_USER", 20)
    full = await client.post(
        "/api/student/uploads", params={"filename": "d.pdf"}, content=b"%PDF-" + b"d" * 20
    )
    assert full.status_code == 413 and "storage is full" in full.text


async def test_f20_uploaded_workbook_is_not_opened_in_the_api_process(
    monkeypatch: pytest.MonkeyPatch, production_isolation: None
) -> None:
    from ezo_api.agents import convert_office

    async def files(ctx, mimes):  # type: ignore[no-untyped-def]
        return [SimpleNamespace(storage_key="k", filename="t.xlsx", title="t", id="1")]

    async def storage_get(key):  # type: ignore[no-untyped-def]
        raise AssertionError("the workbook bytes must not even be loaded")

    monkeypatch.setattr(convert_office, "_files", files)
    ctx = SimpleNamespace(
        tools=SimpleNamespace(services=SimpleNamespace(storage=SimpleNamespace(get=storage_get))),
        turn=SimpleNamespace(text="sort by A"),
    )
    assert await convert_office.run_sheet_action(ctx, SimpleNamespace()) is False
