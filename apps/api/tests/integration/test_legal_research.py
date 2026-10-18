"""LegalResearchAgent and the official-source API end to end (fake model, scripted website)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.main import create_app
from ezo_api.providers.base import ModelProvider
from ezo_api.services import Services
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat
from tests.official_fixtures import (
    LRU_682,
    UZ_LATIN,
    FakeSite,
    Sleeps,
    amended,
    html,
    with_status,
)


@dataclass
class Legal:
    client: AsyncClient
    site: FakeSite
    services: Services


@pytest.fixture
async def legal(database_url: str, providers: dict[str, ModelProvider]) -> AsyncIterator[Legal]:
    settings = make_settings(database_url, EZO_OFFICIAL_SOURCES="lexuz")
    app: FastAPI = create_app(settings, providers=providers)
    services: Services = app.state.services
    site = FakeSite()
    site.routes[f"/docs/{LRU_682}"] = html(UZ_LATIN)
    services.official.fetcher = site.fetcher()
    services.official._sleep = Sleeps()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            yield Legal(client, site, services)
    finally:
        await services.db.dispose()


def system_of(fake: FakeProvider) -> str:
    return fake.requests[-1].system or ""


async def sync(legal: Legal, *ids: str, language: str = "uz") -> dict[str, object]:
    response = await legal.client.post(
        "/api/official/sources/lexuz/sync",
        json={"document_ids": list(ids), "language": language},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_without_official_documents_ezo_says_so(
    legal: Legal, fake_anthropic: FakeProvider
) -> None:
    events = await stream_chat(legal.client, message="Mehnat kodeksida taʼtil necha kun?")
    meta = events[0][1]
    assert meta["agent"] == "legal_research" and meta["requested_agent_available"] is True
    assert "No synchronized official legal documents" in system_of(fake_anthropic)
    assert legal.site.log == []  # nothing fetched without a reason


async def test_answer_uses_official_text_with_metadata_and_live_check(
    legal: Legal, fake_anthropic: FakeProvider
) -> None:
    run = await sync(legal, LRU_682)
    assert run["status"] == "completed" and run["counts"]["new"] == 1  # type: ignore[index]

    fake_anthropic.reply = "Qonunga koʻra hujjatlar milliy bazada eʼlon qilinadi [1]."
    events = await stream_chat(
        legal.client,
        message="Normativ-huquqiy hujjatlar toʻgʻrisidagi qonunda rasmiy eʼlon qilish haqida "
        "nima deyilgan?",
    )
    assert events[0][1]["agent"] == "legal_research"
    request = fake_anthropic.requests[-1]
    assert request.model == "claude-opus-5-5"  # legal answers use the reasoning route
    system = request.system or ""
    assert "Official document: Normativ-huquqiy hujjatlar toʻgʻrisida" in system
    assert "Number: O‘RQ-682" in system and "Adopted: 2021-04-20" in system
    assert "Status: not confirmed" in system and "NEVER say the act is currently in force" in system
    assert f"Official URL: https://lex.uz/docs/{LRU_682}" in system
    assert "re-checked live" in system
    assert legal.site.log.count(f"/docs/{LRU_682}") == 2  # sync + live check

    citations = events[-1][1]["message"]["metadata"]["citations"]
    assert citations[0]["url"] == f"https://lex.uz/docs/{LRU_682}"
    assert citations[0]["extra"]["legal"]["document_number"] == "O‘RQ-682"


async def test_failed_live_check_discloses_the_last_verified_time(
    legal: Legal, fake_anthropic: FakeProvider
) -> None:
    await sync(legal, LRU_682)

    def down() -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    legal.site.routes[f"/docs/{LRU_682}"] = down
    legal.services.official.fetcher = legal.site.fetcher()
    await stream_chat(legal.client, message="Normativ-huquqiy hujjatlar qonuni hozir amaldami?")
    system = system_of(fake_anthropic)
    assert "live verification FAILED" in system and "Last verified retrieval: 20" in system
    assert "do not claim the act is currently in force" in system


async def test_cyrillic_question_finds_latin_text(
    legal: Legal, fake_anthropic: FakeProvider
) -> None:
    await sync(legal, LRU_682)
    await stream_chat(
        legal.client, message="Норматив-ҳуқуқий ҳужжатлар тўғрисидаги қонунда расмий эълон қилиш"
    )
    assert "Official document: Normativ-huquqiy hujjatlar toʻgʻrisida" in system_of(fake_anthropic)


async def test_revision_comparison_and_outdated_acts(
    legal: Legal, fake_anthropic: FakeProvider
) -> None:
    await sync(legal, LRU_682)
    legal.site.routes[f"/docs/{LRU_682}"] = html(amended(UZ_LATIN))
    second = await sync(legal, LRU_682)
    assert second["counts"]["amended"] == 1  # type: ignore[index]
    await stream_chat(
        legal.client,
        message="Normativ-huquqiy hujjatlar qonunining eski va yangi tahririni solishtir",
    )
    system = system_of(fake_anthropic)
    assert "Revision comparison of O‘RQ-682" in system and "1 added" in system
    assert "not official amendment dates" in system

    # A repealed act is left out of current-law answers, but found for history questions.
    legal.site.routes["/docs/900"] = html(
        with_status(UZ_LATIN.replace("Normativ-huquqiy", "Davlat xaridlari"), "Kuchini yoʻqotgan")
    )
    await sync(legal, "900")
    await stream_chat(legal.client, message="Davlat xaridlari hujjatlar qonuni nima deydi?")
    assert "REPEALED" not in system_of(fake_anthropic)
    await stream_chat(legal.client, message="Davlat xaridlari hujjatlar qonunining oldingi tahriri")
    assert "Status: REPEALED (no longer in force)" in system_of(fake_anthropic)


async def test_official_api_lists_reviews_documents_and_revisions(legal: Legal) -> None:
    sources = (await legal.client.get("/api/official/sources")).json()
    by_key = {s["key"]: s for s in sources}
    assert by_key["lexuz"]["enabled"] is True and by_key["lexuz"]["access"] == "public_web_pages"
    assert "Not verified" in by_key["lexuz"]["review"]["robots_txt"]
    for key in ("govuz", "presidentuz", "eqaror", "ministries"):
        assert by_key[key]["can_be_enabled"] is False and by_key[key]["enabled"] is False

    refused = await legal.client.post(
        "/api/official/sources/govuz/sync", json={"document_ids": ["1"]}
    )
    assert refused.status_code == 400
    bad = await legal.client.post(
        "/api/official/sources/lexuz/sync", json={"document_ids": ["../x"]}
    )
    assert bad.status_code == 400

    await sync(legal, LRU_682)
    documents = (await legal.client.get("/api/official/documents")).json()
    assert len(documents) == 1 and documents[0]["document_number"] == "O‘RQ-682"
    detail = (await legal.client.get(f"/api/official/documents/{documents[0]['id']}")).json()
    assert [r["revision_number"] for r in detail["revisions"]] == [1]
    assert detail["provenance"]["connector"] == "lexuz"
    check = await legal.client.post(f"/api/official/documents/{documents[0]['id']}/verify")
    assert check.json()["state"] == "verified"
    runs = (await legal.client.get("/api/official/runs")).json()
    assert runs[0]["status"] == "completed"
    missing = await legal.client.get(f"/api/official/documents/{uuid.uuid4()}")
    assert missing.status_code == 404


async def test_sources_are_off_by_default(client: AsyncClient) -> None:
    response = await client.post(
        "/api/official/sources/lexuz/sync", json={"document_ids": [LRU_682]}
    )
    assert response.status_code == 409
    assert "EZO_OFFICIAL_SOURCES=lexuz" in response.json()["error"]["message"]
    sources = (await client.get("/api/official/sources")).json()
    assert not any(s["enabled"] for s in sources)
