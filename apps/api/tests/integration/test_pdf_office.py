"""EZO Office PDF operations through chat: attachments, page identity, artifacts with
provenance, offline operation and honest refusals."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat
from tests.integration.test_document_agent import created, upload
from tests.pdf_fixtures import encrypted, make_pdf, texts_of

A = make_pdf(["Alpha one", "Alpha two"], title="A")
B = make_pdf(["Beta one", "Beta two"])
C = make_pdf(["Gamma one"])


def system_of(provider: FakeProvider) -> str:
    return provider.requests[-1].system or ""


async def download(client: AsyncClient, artifact: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    detail = (await client.get(f"/api/artifacts/{artifact['id']}")).json()
    response = await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")
    assert response.status_code == 200
    return detail, response.content


async def test_scenario_a_merge_three_attached_pdfs_and_delete_page_two(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    ids = [
        (await upload(client, name, data))["id"]
        for name, data in (("a.pdf", A), ("b.pdf", B), ("c.pdf", C))
    ]
    fake_anthropic.replies = ["Tayyor: 3 ta PDF birlashtirildi, 2-bet olib tashlandi."]
    events = await stream_chat(client, message="Birlashtir va 2-betni olib tashla", attachments=ids)
    assert events[0][1]["agent"] == "document"
    [artifact] = created(events)
    detail, data = await download(client, artifact)
    assert texts_of(data) == ["Alpha one", "Beta one", "Beta two", "Gamma one"]
    version = detail["current_version"]
    assert version["filename"].endswith(".pdf")
    meta = version["generation_metadata"]
    assert meta["operation"] == "pdf" and [s["op"] for s in meta["steps"]] == ["merge", "delete"]
    assert [i["id"] for i in meta["inputs"]] == ids and all(
        len(i["sha256"]) == 64 for i in meta["inputs"]
    )
    assert meta["verification"] == {"reopened": True, "page_count": 4, "expected_pages": 4}
    assert {e["name"] for e in version["exports"]} >= {"preview-1", "preview-4"}
    # The reply model was told the facts; it did not do the work.
    assert len(fake_anthropic.requests) == 1
    assert "merged in the given order" in system_of(fake_anthropic)
    # The originals are untouched.
    original = await client.get(f"/api/knowledge/documents/{ids[0]}")
    assert original.status_code == 200
    # Attachments are recorded on the user's message.
    conversation = events[0][1]["conversation_id"]
    messages = (await client.get(f"/api/conversations/{conversation}/messages")).json()
    user_message = next(m for m in messages if m["role"] == "user")
    assert user_message["metadata"]["attachments"] == ids


async def test_follow_up_works_on_ezos_latest_pdf(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    ids = [(await upload(client, n, d))["id"] for n, d in (("a.pdf", A), ("b.pdf", B))]
    first = await stream_chat(client, message="PDFlarni birlashtir", attachments=ids)
    conversation = first[0][1]["conversation_id"]
    events = await stream_chat(
        client,
        message="Endi oxirgi betni o'chir va sahifa raqamlarini qo'y",
        conversation_id=conversation,
    )
    [artifact] = created(events)
    _, data = await download(client, artifact)
    pages = texts_of(data)
    assert len(pages) == 3
    for number, (page, start) in enumerate(
        zip(pages, ["Alpha one", "Alpha two", "Beta one"], strict=True), start=1
    ):
        assert page.startswith(start) and page.rstrip().endswith(str(number))


async def test_scenario_e_pdf_operations_work_without_any_api_key(database_url: str) -> None:
    app: FastAPI = create_app(make_settings(database_url), providers={})
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            doc = await upload(client, "hisobot.pdf", make_pdf(["One", "Two", "Three"]))
            events = await stream_chat(
                client, message="3-betni birinchi betga ko'chir", attachments=[doc["id"]]
            )
            [artifact] = created(events)
            _, data = await download(client, artifact)
            assert texts_of(data) == ["Three", "One", "Two"]
    finally:
        await app.state.services.db.dispose()


async def test_password_protected_pdf_is_refused_honestly(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    doc = await upload(client, "secret.pdf", encrypted(A))
    other = await upload(client, "b.pdf", B)
    events = await stream_chat(
        client, message="Shu PDFlarni birlashtir", attachments=[doc["id"], other["id"]]
    )
    assert created(events) == []
    assert "password" in system_of(fake_anthropic)


async def test_missing_files_are_not_invented(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    events = await stream_chat(client, message="PDFdagi 2-betni o'chir")
    assert events[0][1]["agent"] == "document"
    assert created(events) == []
    assert "no PDF file was attached or found" in system_of(fake_anthropic)


async def test_someone_elses_attachment_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/chat/stream",
        json={"message": "Birlashtir", "attachments": ["00000000-0000-0000-0000-000000000001"]},
    )
    assert response.status_code == 404


async def test_page_count_question_is_answered_from_the_file(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    doc = await upload(client, "a.pdf", make_pdf(["x", "y", "z"]))
    events = await stream_chat(
        client, message="Bu PDF nechta betdan iborat?", attachments=[doc["id"]]
    )
    assert created(events) == []
    assert "3 pages" in system_of(fake_anthropic)
