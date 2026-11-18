"""Chat/knowledge uploads of PDF/DOCX/EPUB/images go to the isolated document worker.

Never parsed in the API process: without the worker (compose profile "documents") they are
refused with a clear "how to turn it on"; with it, they are queued for the worker and become
an ordinary indexed knowledge document the chat can use.
"""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from ezo_api.documents import isolation
from ezo_api.main import create_app
from ezo_api.settings import Settings
from ezo_api.student.ingestion import StudentIngestion
from tests.conftest import make_settings
from tests.integration.test_student_v1 import DATA, extracted


@pytest.fixture
def production_isolation() -> Iterator[None]:
    """Like the real API: no in-process native parsing at all."""
    token = isolation._FIXTURES.set(False)
    try:
        yield
    finally:
        isolation._FIXTURES.reset(token)


def test_compose_profiles_turn_the_worker_on() -> None:
    def setting(value: str) -> bool:
        return Settings(_env_file=None, EZO_DOCUMENT_WORKER=value).document_worker  # type: ignore[call-arg]

    assert setting("documents") and setting("voice,documents") and setting("true")
    assert not setting("") and not setting("voice") and not setting("student")


async def test_without_the_worker_a_pdf_is_refused_with_how_to_enable_it(
    client: AsyncClient, production_isolation: None
) -> None:
    response = await client.post(
        "/api/knowledge/documents", files={"file": ("book.pdf", DATA, "application/pdf")}
    )
    assert response.status_code == 422
    error = response.json()["error"] if "error" in response.json() else response.json()["detail"]
    assert error["code"] == "isolation_unavailable"
    assert "COMPOSE_PROFILES=documents" in error["message"]
    # Plain text still works without the worker.
    text = await client.post(
        "/api/knowledge/documents", files={"file": ("note.txt", b"Salom", "text/plain")}
    )
    assert text.status_code == 201


async def test_with_the_worker_a_pdf_is_queued_then_indexed_for_the_chat(
    database_url: str, providers: dict, production_isolation: None
) -> None:
    from httpx import ASGITransport

    app = create_app(
        make_settings(database_url, EZO_DOCUMENT_WORKER="documents"), providers=providers
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status = (await client.get("/api/knowledge/status")).json()
        assert ".pdf" in status["allowed_extensions"] and ".jpg" in status["allowed_extensions"]

        response = await client.post(
            "/api/knowledge/documents", files={"file": ("book.pdf", DATA, "application/pdf")}
        )
        assert response.status_code == 201, response.text
        document = response.json()["document"]
        assert document["status"] == "queued"

        # What the worker does: claim, extract in its isolated container, publish.
        jobs = StudentIngestion(app.state.services.db)
        lease = await jobs.claim("local-docs-1")
        assert lease is not None
        await jobs.publish_extraction(lease, extracted())

        indexed = (await client.get(f"/api/knowledge/documents/{document['id']}")).json()
        assert indexed["status"] == "indexed" and indexed["chunk_count"] >= 1

        # Chat file tools (merge/split/convert) can still read the original bytes.
        import uuid

        from ezo_api.db.models import KnowledgeDocument

        async with app.state.services.db.sessionmaker() as session:
            stored = await session.get(KnowledgeDocument, uuid.UUID(document["id"]))
            assert stored is not None and stored.storage_key
            assert await app.state.services.storage.get(stored.storage_key) == DATA

        # The same file again is recognised, not queued twice.
        again = await client.post(
            "/api/knowledge/documents", files={"file": ("book.pdf", DATA, "application/pdf")}
        )
        assert again.status_code == 200 and again.json()["document"]["id"] == document["id"]
    await app.state.services.db.dispose()
