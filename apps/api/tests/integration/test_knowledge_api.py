from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from ezo_api.db.models import KnowledgeChunk, ToolCall
from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.fakes import FakeProvider
from tests.files import PNG_1PX, make_docx, make_pdf
from tests.integration.helpers import count_vectors, stream_chat

FACT = "EZO loyihasining ichki kod nomi Samarqand-7 bo‘lib, uni Aziz boshqaradi."


async def upload(client: AsyncClient, name: str, data: bytes, **form: str):  # type: ignore[no-untyped-def]
    return await client.post("/api/knowledge/documents", files={"file": (name, data)}, data=form)


async def test_upload_ingests_and_indexes(client: AsyncClient, app: FastAPI) -> None:
    response = await upload(
        client, "loyiha.pdf", make_pdf([FACT, "Ikkinchi sahifa: muddat dekabr."])
    )
    assert response.status_code == 201, response.text
    body = response.json()
    document = body["document"]
    assert body["duplicate"] is False
    assert document["status"] == "indexed"
    assert document["chunk_count"] >= 1
    assert document["current_revision"] == 1
    assert document["metadata"]["pages"] == 2
    assert document["metadata"]["embedding_model"] == "openai:text-embedding-3-small"

    detail = (await client.get(f"/api/knowledge/documents/{document['id']}")).json()
    assert detail["revisions"][0]["current"] is True
    assert "Samarqand-7" in detail["chunks_preview"][0]["text"]

    assert await count_vectors(app) == document["chunk_count"]

    status = (await client.get("/api/knowledge/status")).json()
    assert status["semantic_search"] is True and status["documents"] == 1
    assert status["vector_store"] in {"local", "pgvector"}


async def test_invalid_and_oversized_uploads(client: AsyncClient, database_url: str) -> None:
    bad = await upload(client, "virus.exe", b"MZ")
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "unsupported_type"

    fake = await upload(client, "fake.pdf", b"not a pdf at all")
    assert fake.status_code == 422 and fake.json()["error"]["code"] == "wrong_type"

    small = create_app(
        make_settings(database_url, EZO_MAX_UPLOAD_MB=1),
        providers={"anthropic": FakeProvider(name="anthropic")},
    )
    async with AsyncClient(transport=ASGITransport(app=small), base_url="http://t") as ac:
        big = await upload(ac, "big.txt", b"a" * (1024 * 1024 + 10))
        assert big.status_code == 413
        assert "1 MB" in big.json()["error"]["message"]
    await small.state.services.db.dispose()


async def test_duplicate_upload_is_detected(client: AsyncClient) -> None:
    first = await upload(client, "a.txt", FACT.encode())
    second = await upload(client, "copy.txt", FACT.encode())
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["document"]["id"] == first.json()["document"]["id"]
    assert len((await client.get("/api/knowledge/documents")).json()) == 1


async def test_changed_file_creates_new_revision_and_hides_old(
    client: AsyncClient, app: FastAPI
) -> None:
    v1 = (await upload(client, "narxlar.txt", b"Kofe narxi 15000 so'm.")).json()["document"]
    v2_response = await upload(client, "narxlar.txt", b"Kofe narxi 18000 so'm, choy 8000 so'm.")
    v2 = v2_response.json()
    assert v2["new_revision"] is True and v2["document"]["id"] == v1["id"]
    assert v2["document"]["current_revision"] == 2

    detail = (await client.get(f"/api/knowledge/documents/{v1['id']}")).json()
    assert [r["revision_number"] for r in detail["revisions"]] == [2, 1]
    assert [r["current"] for r in detail["revisions"]] == [True, False]

    results = (await client.post("/api/knowledge/search", json={"query": "kofe narxi"})).json()[
        "results"
    ]
    assert results and all("18000" in r["excerpt"] for r in results)
    assert results[0]["revision_number"] == 2

    async with app.state.services.db.sessionmaker() as session:  # history kept
        chunks = await session.scalar(select(func.count()).select_from(KnowledgeChunk))
        assert chunks == 2


async def test_hybrid_search_returns_provenance(client: AsyncClient) -> None:
    await upload(client, "loyiha.docx", make_docx("Loyiha", [FACT, "Byudjet 120 million so'm."]))
    await upload(client, "boshqa.txt", b"Toshkentda ob-havo issiq.")
    response = (
        await client.post("/api/knowledge/search", json={"query": "Samarqand-7 kod nomi"})
    ).json()
    assert response["mode"] == "hybrid"
    top = response["results"][0]
    assert "Samarqand-7" in top["excerpt"]
    assert top["title"] == "Loyiha" and top["kind"] == "file"
    assert top["revision_number"] == 1 and top["chunk_index"] == 0
    assert top["document_id"] and top["date"]


async def test_delete_removes_document_vectors_and_file(client: AsyncClient, app: FastAPI) -> None:
    document = (await upload(client, "a.txt", FACT.encode())).json()["document"]
    storage_root = Path(app.state.services.settings.storage_dir)
    assert any(storage_root.rglob("*.txt"))  # noqa: ASYNC240
    assert (await client.delete(f"/api/knowledge/documents/{document['id']}")).status_code == 204
    assert (await client.get(f"/api/knowledge/documents/{document['id']}")).status_code == 404
    assert not any(storage_root.rglob("*.txt"))  # noqa: ASYNC240
    assert await count_vectors(app) == 0


async def test_reindex_and_partial_without_embeddings(
    client: AsyncClient, fake_openai: FakeProvider
) -> None:
    fake_openai.embed_fail = True
    document = (await upload(client, "a.txt", FACT.encode())).json()["document"]
    assert document["status"] == "partial"
    assert "Keyword search works" in document["error"]
    # keyword search still finds it
    results = (await client.post("/api/knowledge/search", json={"query": "Samarqand-7"})).json()
    assert results["mode"] == "keyword" and results["results"]

    fake_openai.embed_fail = False
    reindexed = (await client.post(f"/api/knowledge/documents/{document['id']}/reindex")).json()
    assert reindexed["status"] == "indexed" and reindexed["current_revision"] == 1


async def test_images_and_broken_files_report_status(client: AsyncClient) -> None:
    image = (await upload(client, "photo.png", PNG_1PX)).json()["document"]
    assert image["status"] == "needs_ocr"
    assert "OCR" in image["error"]
    broken = (await upload(client, "broken.pdf", b"%PDF-1.7 broken body")).json()["document"]
    assert broken["status"] == "failed"
    assert "PDF" in broken["error"]


async def test_project_scoping(client: AsyncClient) -> None:
    project = (await client.post("/api/projects", json={"name": "Maxfiy loyiha"})).json()
    await upload(
        client, "p.txt", b"Loyiha paroli emas, balki rang: binafsha.", project_id=project["id"]
    )
    outside = (await client.post("/api/knowledge/search", json={"query": "binafsha rang"})).json()
    inside = (
        await client.post(
            "/api/knowledge/search", json={"query": "binafsha rang", "project_id": project["id"]}
        )
    ).json()
    assert outside["results"] == []
    assert inside["results"]
    sources = (await client.get("/api/knowledge/sources")).json()
    assert sources[0]["project_id"] == project["id"] and sources[0]["documents"] == 1


async def test_chat_uses_files_and_verifies_citations(
    client: AsyncClient, fake_anthropic: FakeProvider, app: FastAPI
) -> None:
    await upload(client, "loyiha.txt", FACT.encode())
    fake_anthropic.reply = "Kod nomi Samarqand-7 [1]. Boshqa da'vo [4]."
    events = await stream_chat(client, message="Loyihaning ichki kod nomi nima? Kim boshqaradi?")
    system = fake_anthropic.requests[-1].system or ""
    assert "[1] loyiha" in system and "Samarqand-7" in system
    assert '<source n="1">' in system and "never invent a source" in system

    assert [d["stage"] for n, d in events if n == "activity"] == ["searching"]
    done = events[-1][1]["message"]
    assert done["content"] == "Kod nomi Samarqand-7 [1]. Boshqa da'vo."
    citations = done["metadata"]["citations"]
    assert len(citations) == 1 and citations[0]["title"] == "loyiha"
    assert citations[0]["kind"] == "file" and citations[0]["revision_number"] == 1

    run = (await client.get(f"/api/agent-runs/{done['agent_run_id']}")).json()
    assert run["tool_calls"][0]["tool"] == "knowledge_search"
    steps = {s["name"]: s["summary"] for s in run["steps"]}
    assert "removed=[4]" in steps["verify_citations"]
    async with app.state.services.db.sessionmaker() as session:
        logged = (await session.scalars(select(ToolCall))).all()
        assert [t.tool_name for t in logged] == ["knowledge_search"]
        assert logged[0].status == "ok"


async def test_unrelated_chat_does_not_inject_files(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await upload(client, "loyiha.txt", FACT.encode())
    events = await stream_chat(client, message="Salom, kayfiyating qalay?")
    assert [d["stage"] for n, d in events if n == "activity"] == ["searching"]  # files checked
    assert "<source" not in (fake_anthropic.requests[-1].system or "")
