"""Real DB worker execution and fail-closed native prerequisite checks."""

import asyncio
import subprocess
import sys
from unittest.mock import patch

import pytest
from sqlalchemy import update

from ezo_api.db.models import DocumentRevision, KnowledgeDocument
from ezo_api.db.session import Database
from ezo_api.documents import isolation
from ezo_api.documents.process_limits import run_native
from ezo_api.knowledge.jobs.service import DocumentJobs
from ezo_api.knowledge.jobs.worker import StoredTextWorker, paragraph_spans
from tests.integration.test_document_jobs import SPANS, TEXT, expire, queued


@pytest.fixture
async def db(database_url):
    database = Database(database_url)
    yield database
    await database.dispose()


async def test_real_stored_text_worker_completes_readable_unicode_result(db):
    scope, jobs, job = await queued(db)
    worker = StoredTextWorker(jobs, "controlled-worker")
    assert await worker.process_one()
    page = await jobs.result_page(scope.user, scope.project, job.id)
    assert page.text == TEXT
    assert page.spans[0] == SPANS[0]
    assert await worker.process_one() is False


async def test_worker_restart_reclaims_crashed_claim_and_fences_old_lease(db):
    scope, jobs, job = await queued(db)
    old = await jobs.claim("crashed-process")
    await expire(db, old)
    assert await StoredTextWorker(DocumentJobs(db), "replacement").process_one()
    state = await jobs.get(scope.user, scope.project, job.id)
    assert state.state == "completed" and state.attempts == 2
    from ezo_api.knowledge.jobs.service import JobError

    with pytest.raises(JobError):
        await jobs.publish(old, TEXT, SPANS)


async def test_worker_cancellation_prevents_publication(db, monkeypatch):
    scope, jobs, job = await queued(db)
    original = jobs.read_input

    async def cancel_during_read(lease):
        value = await original(lease)
        await jobs.cancel(scope.user, scope.project, job.id)
        return value

    monkeypatch.setattr(jobs, "read_input", cancel_during_read)
    assert await StoredTextWorker(jobs, "worker").process_one()
    assert (await jobs.get(scope.user, scope.project, job.id)).state == "cancelled"


async def test_worker_whole_job_deadline_revokes_publication(db, monkeypatch):
    scope, jobs, job = await queued(db)

    async def stalled_read(lease):
        await asyncio.sleep(10)
        return TEXT

    monkeypatch.setattr(jobs, "read_input", stalled_read)
    assert await StoredTextWorker(jobs, "worker", deadline_seconds=0.1).process_one()
    state = await jobs.get(scope.user, scope.project, job.id)
    assert state.state == "queued" and state.error_code == "transient" and state.attempts == 1
    assert await jobs.claim("too-early") is None


async def test_worker_shutdown_stops_idle_polling(db):
    stop = asyncio.Event()
    worker = StoredTextWorker(DocumentJobs(db), "idle", poll_seconds=0.05)
    task = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=2)


async def test_worker_rejects_mutated_source(db):
    scope, jobs, job = await queued(db)
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentRevision)
            .where(DocumentRevision.id == scope.revision)
            .values(raw_text="mutated")
        )
        await session.commit()
    assert await StoredTextWorker(jobs, "worker").process_one()
    assert (await jobs.get(scope.user, scope.project, job.id)).state == "failed"


def test_paragraph_offsets_coalesce_at_bounded_span_limit():
    value = "🙂Ў\n\n" * 2000
    spans = paragraph_spans(value)
    assert len(spans) == 1000 and spans[-1].end == len(value)
    assert value[spans[0].start : spans[0].end] == "🙂Ў"


@pytest.mark.parametrize("hostile", ["import os; os.setsid()", "x=bytearray(1024**3)"])
def test_native_workload_fail_closed_before_hostile_execution(hostile):
    token = isolation._FIXTURES.set(False)
    try:
        with (
            patch.object(
                subprocess, "Popen", side_effect=AssertionError("native execution started")
            ),
            pytest.raises(isolation.IsolationUnavailable),
        ):
            run_native(
                [sys.executable, "-c", hostile], timeout=1, file_limit=1024, stdout_limit=1024
            )
    finally:
        isolation._FIXTURES.reset(token)


async def test_unisolated_api_rejects_documents_before_parsing(client, monkeypatch):
    from tests.integration.test_knowledge_api import upload

    token = isolation._FIXTURES.set(False)
    try:
        response = await upload(client, "hostile.pdf", b"%PDF-pretend")
        assert response.status_code == 422
        assert "isolation_unavailable" in response.text
        response = await upload(client, "book.epub", b"PK-hostile")
        assert response.status_code == 422 and "isolation_unavailable" in response.text
        response = await upload(client, "safe.txt", TEXT.encode())
        assert response.status_code == 201
    finally:
        isolation._FIXTURES.reset(token)


async def test_identical_uploads_stay_in_authorized_project(client):
    from tests.integration.test_knowledge_api import upload

    a = (await client.post("/api/projects", json={"name": "A"})).json()["id"]
    b = (await client.post("/api/projects", json={"name": "B"})).json()["id"]
    first = (await upload(client, "same.txt", TEXT.encode(), project_id=a)).json()["document"]
    second = (await upload(client, "same.txt", TEXT.encode(), project_id=b)).json()["document"]
    assert first["id"] != second["id"]
    assert first["project_id"] == a and second["project_id"] == b


async def test_student_submission_to_durable_worker_and_scoped_reading(client, app):
    token = isolation._FIXTURES.set(False)
    try:
        project = (await client.post("/api/projects", json={"name": "Study"})).json()["id"]
        body = {"text": TEXT, "title": "Uzbek", "project_id": project}
        response = await client.post("/api/student/readings", json=body)
        assert response.status_code == 201, response.text
        job = response.json()
        url = "/api/student/readings/" + job["id"]
        assert (await client.get(url)).status_code == 404
        assert (await client.get(url, params={"project_id": project})).status_code == 409
        worker = StoredTextWorker(DocumentJobs(app.state.services.db), "student")
        assert await worker.process_one()
        result = await client.get(url, params={"project_id": project, "offset": 2, "limit": 6})
        assert result.status_code == 200 and result.json()["text"] == TEXT[2:8]
        duplicate = await client.post("/api/student/readings", json=body)
        assert duplicate.json()["id"] == job["id"] and duplicate.json()["state"] == "completed"
        status = (await client.get("/api/student/status")).json()
        assert status["native_execution"] == "disabled"
    finally:
        isolation._FIXTURES.reset(token)


async def test_student_submission_rejects_foreign_project_and_empty_text(client):
    import uuid

    response = await client.post(
        "/api/student/readings", json={"text": TEXT, "project_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404
    assert (await client.post("/api/student/readings", json={"text": " \n\n "})).status_code == 422


async def test_project_duplicate_deletion_keeps_other_project_file(client, app):
    from tests.integration.test_knowledge_api import upload

    a = (await client.post("/api/projects", json={"name": "A"})).json()["id"]
    b = (await client.post("/api/projects", json={"name": "B"})).json()["id"]
    first = (await upload(client, "shared.txt", TEXT.encode(), project_id=a)).json()["document"]
    second = (await upload(client, "shared.txt", TEXT.encode(), project_id=b)).json()["document"]
    assert (await client.delete("/api/knowledge/documents/" + first["id"])).status_code == 204
    import uuid

    async with app.state.services.db.sessionmaker() as session:
        document = await session.get(KnowledgeDocument, uuid.UUID(second["id"]))
        assert await app.state.services.storage.get(document.storage_key) == TEXT.encode()


def test_direct_official_html_parser_cannot_bypass_isolation():
    from ezo_api.knowledge.parsers.base import ParseError
    from ezo_api.knowledge.parsers.html import parse_html

    token = isolation._FIXTURES.set(False)
    try:
        with (
            patch("trafilatura.extract", side_effect=AssertionError("Extractor reached")),
            pytest.raises(ParseError) as error,
        ):
            parse_html(b"<html>untrusted website</html>", "official.html")
        assert error.value.code == "isolation_unavailable"
    finally:
        isolation._FIXTURES.reset(token)
