"""OCR end to end with the real Tesseract engine: scanned uploads become searchable with
page provenance, chat reads attached images, and without an engine EZO says so."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.documents.pdf import engine
from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat
from tests.integration.test_document_agent import created, upload
from tests.ocr_fixtures import (
    ENGLISH,
    UZ_CYRILLIC,
    UZ_LATIN,
    needs_tesseract,
    page_image,
    png,
    recall,
)
from tests.pdf_fixtures import make_pdf

pytestmark = needs_tesseract


@pytest.fixture
async def ocr_client(
    database_url: str, fake_anthropic: FakeProvider, fake_openai: FakeProvider
) -> AsyncIterator[tuple[AsyncClient, FastAPI]]:
    app = create_app(
        make_settings(database_url, EZO_OCR_PROVIDER="auto"),
        providers={"anthropic": fake_anthropic, "openai": fake_openai},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, app
    await app.state.services.db.dispose()


async def test_scanned_pdf_page_is_ocrd_searchable_and_cited(
    ocr_client: tuple[AsyncClient, FastAPI],
) -> None:
    client, _ = ocr_client
    text_page = make_pdf(["Kirish: ushbu hujjat skanerlangan ilovani o'z ichiga oladi."])
    scan = engine.images_to_pdf([png(page_image(UZ_LATIN))]).data
    mixed = engine.merge([text_page, scan]).data
    document = await upload(client, "qaror.pdf", mixed)
    assert document["status"] in ("indexed", "partial"), document
    ocr = document["metadata"]["ocr"]
    assert ocr["pages"] == [2] and ocr["engine"] == "tesseract"
    assert ocr["mean_confidence"] >= 80 and ocr["languages"][0].startswith("uzb")

    pages = (await client.get(f"/api/knowledge/documents/{document['id']}/ocr")).json()
    [page] = pages
    assert page["page"] == 2 and page["current"] and page["lines"]
    assert recall(UZ_LATIN, page["text"]) >= 0.9

    results = (
        await client.post("/api/knowledge/search", json={"query": "ta'lim tizimini rivojlantirish"})
    ).json()["results"]
    top = results[0]
    assert top["page_start"] <= 2 <= (top["page_end"] or top["page_start"])
    assert "rivojlantirish" in top["excerpt"]
    assert "text read by OCR" in top["location"]


async def test_chat_reads_an_attached_cyrillic_photo(
    ocr_client: tuple[AsyncClient, FastAPI], fake_anthropic: FakeProvider
) -> None:
    client, _ = ocr_client
    photo = await upload(client, "skan.png", png(page_image(UZ_CYRILLIC, skew=2)))
    assert photo["status"] in ("indexed", "partial")
    fake_anthropic.replies = ["Mana rasmdagi matn."]
    events = await stream_chat(
        client, message="Rasmdagi matnni chiqarib ber", attachments=[photo["id"]]
    )
    assert events[0][1]["agent"] == "document"
    [artifact] = created(events)
    detail = (await client.get(f"/api/artifacts/{artifact['id']}")).json()
    version = detail["current_version"]
    assert version["filename"].endswith(".txt")
    meta = version["generation_metadata"]
    assert meta["operation"] == "ocr" and meta["engine"]["reused_from_ingestion"] is True
    assert meta["inputs"][0]["id"] == photo["id"] and "not a calibrated" in meta["confidence_note"]
    text = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).text
    assert recall(UZ_CYRILLIC, text) >= 0.9
    system = fake_anthropic.requests[-1].system or ""
    assert "RECOGNISED TEXT" in system and "never fill in unreadable parts" in system
    assert "қарор" in system


async def test_unreadable_image_is_not_invented(
    ocr_client: tuple[AsyncClient, FastAPI], fake_anthropic: FakeProvider
) -> None:
    client, _ = ocr_client
    blank = await upload(client, "bo'sh.png", png(page_image([])))
    assert blank["status"] == "needs_ocr"
    assert "ran but found no readable text" in blank["error"]
    events = await stream_chat(
        client, message="Bu rasmdagi matnni o'qib ber", attachments=[blank["id"]]
    )
    assert created(events) == []
    assert "recognised no text" in (fake_anthropic.requests[-1].system or "")


async def test_language_named_by_the_user_is_used(
    ocr_client: tuple[AsyncClient, FastAPI], fake_anthropic: FakeProvider
) -> None:
    client, _ = ocr_client
    photo = await upload(client, "en.png", png(page_image(ENGLISH)))
    await stream_chat(
        client, message="Rasmdagi matnni inglizcha tanib ol", attachments=[photo["id"]]
    )
    system = fake_anthropic.requests[-1].system or ""
    assert "language packs eng" in system


async def test_without_an_ocr_engine_scans_stay_honestly_unread(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    # The default test settings turn OCR off (EZO_OCR_PROVIDER=none).
    photo = await upload(client, "skan.png", png(page_image(UZ_LATIN)))
    assert photo["status"] == "needs_ocr"
    assert "OCR is not available on this server" in photo["error"]
    events = await stream_chat(
        client, message="Rasmdagi matnni chiqarib ber", attachments=[photo["id"]]
    )
    assert created(events) == []
    system = fake_anthropic.requests[-1].system or ""
    assert "OCR could not read" in system and "turned off" in system
    status = (await client.get("/api/status")).json()
    assert status["ocr"]["available"] is False
