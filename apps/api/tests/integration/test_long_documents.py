"""Long files are covered completely: map-reduce summaries, part-by-part translation,
answers searched across the whole file, and jobs that continue after a failure."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from ezo_api.db.models import LongDocPart
from ezo_api.documents.longdoc import split_parts
from ezo_api.main import create_app
from ezo_api.providers.errors import ProviderError, ProviderErrorKind
from ezo_api.providers.types import ChatRequest
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat
from tests.integration.test_document_agent import created, upload


def long_text() -> str:
    return "\n\n".join(
        f"{n}-modda. Modda {n} haqida\n"
        + " ".join(f"band{n}x{i}" for i in range(700))
        + (" Ijara narxi oyiga 7 777 777 so'm." if n == 6 else "")
        for n in range(1, 8)
    )


TEXT = long_text()
PARTS = split_parts(TEXT)


@dataclass
class Flaky(FakeProvider):
    fail_on_call: int | None = None

    async def stream_chat(self, request: ChatRequest):  # type: ignore[no-untyped-def,override]
        if self.fail_on_call is not None and len(self.requests) + 1 == self.fail_on_call:
            self.requests.append(request)
            raise ProviderError(self.name, ProviderErrorKind.UNAVAILABLE, "down", 503)
        async for event in super().stream_chat(request):
            yield event


@pytest.fixture
async def flaky_app(database_url: str) -> AsyncIterator[tuple[AsyncClient, FastAPI, Flaky]]:
    provider = Flaky(name="anthropic", reply="Qisqa mazmun.")
    app = create_app(make_settings(database_url), providers={"anthropic": provider})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, app, provider
    await app.state.services.db.dispose()


async def test_the_whole_long_file_is_summarised_part_by_part(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    assert len(TEXT) > 20_000 and len(PARTS) >= 3
    document = await upload(client, "qonun.txt", TEXT.encode())
    fake_anthropic.replies = [f"Qism {i + 1} xulosasi." for i in range(len(PARTS))] + [
        "## Umumiy\nYakuniy xulosa: ijara 7 777 777 so'm.",
        "Mana xulosa.",
    ]
    events = await stream_chat(
        client, message="Shu faylning qisqacha mazmunini yoz", attachments=[document["id"]]
    )
    assert events[0][1]["agent"] == "document"
    sent = [r.messages[0].content for r in fake_anthropic.requests[: len(PARTS)]]
    for part, content in zip(PARTS, sent, strict=True):
        assert part.text[-40:] in content  # every part, to its last word
    combine = fake_anthropic.requests[len(PARTS)].messages[0].content
    assert all(f"Qism {i + 1} xulosasi." in combine for i in range(len(PARTS)))
    system = fake_anthropic.requests[-1].system or ""
    assert "EZO read ALL of" in system and f"{len(PARTS)} parts" in system
    assert "Yakuniy xulosa: ijara 7 777 777 so'm." in system
    assert "Only the first" not in system


async def test_a_failed_job_continues_where_it_stopped(
    flaky_app: tuple[AsyncClient, FastAPI, Flaky],
) -> None:
    client, app, provider = flaky_app
    document = await upload(client, "qonun.txt", TEXT.encode())
    provider.fail_on_call = 3  # parts 1 and 2 succeed, part 3 fails
    await stream_chat(
        client, message="Shu faylning qisqacha mazmunini yoz", attachments=[document["id"]]
    )
    async with app.state.services.db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(LongDocPart)) == 2
    reply_system = provider.requests[-1].system or ""
    assert "stopped after 2 of" in reply_system and "continues" in reply_system

    provider.fail_on_call = None
    before = len(provider.requests)
    await stream_chat(
        client, message="Shu faylning qisqacha mazmunini yoz", attachments=[document["id"]]
    )
    new = provider.requests[before:]
    # The remaining parts, the final combination and the reply; parts 1-2 are not re-sent.
    assert len(new) == (len(PARTS) - 2) + 1 + 1
    assert PARTS[0].text[-40:] not in new[0].messages[0].content
    assert "2 part(s) reused" in (new[-1].system or "")


async def test_long_translation_covers_every_part(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    document = await upload(client, "qonun.txt", TEXT.encode())
    fake_anthropic.replies = [
        f"## Article {i + 1}\nTranslated part {i + 1}." for i in range(len(PARTS))
    ] + ["Tayyor."]
    events = await stream_chat(
        client, message="Shu faylni ingliz tiliga tarjima qil", attachments=[document["id"]]
    )
    [artifact] = created(events)
    detail = (await client.get(f"/api/artifacts/{artifact['id']}")).json()
    meta = detail["current_version"]["generation_metadata"]
    assert meta["long_document"]["parts"] == len(PARTS) and meta["partial"] is False
    exported = (
        await client.get(f"/api/artifacts/{artifact['id']}/versions/1/exports/markdown")
    ).text
    assert all(f"Translated part {i + 1}." in exported for i in range(len(PARTS)))


async def test_questions_search_the_whole_long_file(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    document = await upload(client, "qonun.txt", TEXT.encode())
    assert TEXT.index("7 777 777") > 20_000  # far beyond what fits in one prompt
    await stream_chat(
        client, message="Bu faylda ijara narxi qancha deyilgan?", attachments=[document["id"]]
    )
    system = fake_anthropic.requests[-1].system or ""
    assert "searched the WHOLE file" in system and "7 777 777" in system
