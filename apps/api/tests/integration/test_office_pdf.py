"""Word/Excel → PDF through chat, with no AI provider: LibreOffice layout when installed,
an honest text-only fallback when not."""

from __future__ import annotations

import io

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader

from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.integration.helpers import stream_chat
from tests.integration.test_document_agent import created, upload
from tests.office import requires_office
from tests.office_fixtures import official_letter_docx, report_xlsx


async def run(database_url: str, converter: str, filename: str, data: bytes, message: str):  # type: ignore[no-untyped-def]
    app: FastAPI = create_app(
        make_settings(database_url, EZO_OFFICE_CONVERTER=converter), providers={}
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            document = await upload(client, filename, data)
            events = await stream_chat(client, message=message, attachments=[document["id"]])
            artifacts = created(events)
            details = []
            for artifact in artifacts:
                detail = (await client.get(f"/api/artifacts/{artifact['id']}")).json()
                pdf = (
                    await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")
                ).content
                details.append((detail["current_version"], pdf))
            status = (await client.get("/api/status")).json()
            return details, status
    finally:
        await app.state.services.db.dispose()


@requires_office
async def test_word_to_pdf_keeps_the_layout(database_url: str) -> None:
    [(version, pdf)], status = await run(
        database_url, "auto", "xat.docx", official_letter_docx(), "Shu Word faylni PDF ga aylantir"
    )
    assert status["office_converter"]["available"] is True
    assert version["filename"] == "xat.pdf"
    meta = version["generation_metadata"]
    assert meta["operation"] == "docx_to_pdf" and meta["pages"] == 2
    assert meta["engine"].startswith("LibreOffice") and meta["verification"]["reopened"]
    assert {e["name"] for e in version["exports"]} >= {"preview-1", "preview-2"}
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) == 2 and "XATIRCHI TUMANI HOKIMLIGI" in pages[1].extract_text()


@requires_office
async def test_excel_to_pdf(database_url: str) -> None:
    [(version, pdf)], _ = await run(
        database_url, "auto", "aholi.xlsx", report_xlsx(), "Excel faylni PDF qilib ber"
    )
    assert version["generation_metadata"]["operation"] == "xlsx_to_pdf"
    assert "Jami 345000" in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()


async def test_without_libreoffice_the_fallback_is_labelled(database_url: str) -> None:
    [(version, pdf)], status = await run(
        database_url, "none", "xat.docx", official_letter_docx(), "Shu Word faylni PDF ga aylantir"
    )
    assert status["office_converter"]["available"] is False
    assert version["generation_metadata"]["action"] == "convert"  # EZO's own text-based PDF
    assert pdf.startswith(b"%PDF")
