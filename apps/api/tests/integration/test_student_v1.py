"""Student raw revisions, fencing, cancellation and mocked grounded learning."""

import hashlib
import json
import threading
import uuid

import pytest
from sqlalchemy import func, select, update

from ezo_api.db.models import (
    DocumentJobPublication,
    DocumentRevision,
    KnowledgeChunk,
    StudentRawRevision,
)
from ezo_api.db.session import Database
from ezo_api.documents.executor.protocol import ExecutorError, ExtractionResult, SourceSection
from ezo_api.knowledge.jobs.service import DocumentJobs, JobError
from ezo_api.student.ingestion import StudentIngestion
from ezo_api.student.worker import StudentWorker
from tests.integration.test_document_jobs import expire, seed


@pytest.fixture
async def db(database_url):
    database = Database(database_url)
    yield database
    await database.dispose()


DATA = b"%PDF-small-private-source"
TEXT = "O‘zbekiston 🙂\n\nFotosintez quyosh energiyasini saqlaydi."


def extracted(data=DATA):
    return ExtractionResult(
        source_sha256=hashlib.sha256(data).hexdigest(),
        text=TEXT,
        sections=[
            SourceSection(start=0, end=TEXT.index("\n"), page=1),
            SourceSection(start=TEXT.index("\n") + 2, end=len(TEXT), page=2, heading="Fotosintez"),
        ],
    )


async def raw_queued(db):
    scope = await seed(db)
    jobs = StudentIngestion(db)
    job = await jobs.submit_raw(scope.user, scope.project, "book.pdf", DATA)
    return scope, jobs, job


async def test_raw_registration_is_atomic_idempotent_and_scope_bound(db):
    scope, jobs, job = await raw_queued(db)
    duplicate = await jobs.submit_raw(scope.user, scope.project, "book.pdf", DATA)
    assert duplicate.id == job.id
    assert await DocumentJobs(db).claim("text-worker") is None
    other = await seed(db)
    with pytest.raises(JobError, match="not found"):
        await jobs.submit_raw(other.user, scope.project, "book.pdf", DATA)
    with pytest.raises(JobError):
        await jobs.get(other.user, other.project, job.id)
    with pytest.raises(JobError):
        await jobs.get(scope.user, None, job.id)


async def test_publication_indexes_exact_unicode_offsets_and_preserves_raw_revision(db):
    scope, jobs, job = await raw_queued(db)
    lease = await jobs.claim("native")
    assert await jobs.raw_input(lease) == (DATA, "pdf")
    await jobs.publish_extraction(lease, extracted())
    await jobs.publish_extraction(lease, extracted())  # idempotent ACK
    page = await jobs.result_page(scope.user, scope.project, job.id, offset=2, limit=10)
    assert page.text == TEXT[2:12] and page.spans[0].start == 0
    async with db.sessionmaker() as session:
        raw_revision = await session.get(DocumentRevision, job.input_revision_id)
        assert raw_revision.raw_text == ""
        chunks = list(
            (
                await session.scalars(
                    select(KnowledgeChunk).where(KnowledgeChunk.document_id == job.document_id)
                )
            ).all()
        )
        assert len(chunks) == 2
        for chunk in chunks:
            assert chunk.text == TEXT[chunk.meta["start"] : chunk.meta["end"]]
        assert await session.scalar(select(func.count()).select_from(DocumentJobPublication)) == 1


async def test_wrong_hash_and_expired_lease_never_publish(db):
    scope, jobs, job = await raw_queued(db)
    lease = await jobs.claim("native")
    with pytest.raises(JobError):
        await jobs.publish_extraction(lease, extracted(b"wrong"))
    await expire(db, lease)
    with pytest.raises(JobError):
        await jobs.publish_extraction(lease, extracted())
    replacement = await jobs.claim("replacement")
    await jobs.publish_extraction(replacement, extracted())
    assert (await jobs.get(scope.user, scope.project, job.id)).attempts == 2


async def test_mutated_raw_bytes_rejected_before_execution(db):
    _scope, jobs, job = await raw_queued(db)
    lease = await jobs.claim("native")
    async with db.sessionmaker() as session:
        await session.execute(
            update(StudentRawRevision)
            .where(StudentRawRevision.revision_id == job.input_revision_id)
            .values(data=b"changed")
        )
        await session.commit()
    with pytest.raises(JobError, match="immutable"):
        await jobs.raw_input(lease)


async def test_retry_new_generation_preserves_terminal_history_and_total_budget(db):
    scope, jobs, job = await raw_queued(db)
    lease = await jobs.claim("native")
    await jobs.fail(lease, "invalid_input")
    second = await jobs.retry(scope.user, scope.project, job.id)
    assert second.id != job.id and second.max_attempts == 2
    assert (await jobs.retry(scope.user, scope.project, job.id)).id == second.id
    assert (await jobs.get(scope.user, scope.project, job.id)).state == "failed"
    lease2 = await jobs.claim("native")
    await jobs.cancel(scope.user, scope.project, second.id)
    with pytest.raises(JobError):
        await jobs.publish_extraction(lease2, extracted())
    third = await jobs.retry(scope.user, scope.project, second.id)
    assert third.id not in (job.id, second.id) and third.max_attempts == 1
    await jobs.cancel(scope.user, scope.project, third.id)
    with pytest.raises(JobError, match="budget"):
        await jobs.retry(scope.user, scope.project, third.id)


async def test_worker_physically_cancels_on_owner_cancellation(db):
    import asyncio

    scope, jobs, job = await raw_queued(db)
    started, stopped = threading.Event(), threading.Event()

    class BlockingExecutor:
        def extract(self, data, format, *, cancelled):
            started.set()
            try:
                assert cancelled.wait(5)
                raise ExecutorError("cancelled")
            finally:
                stopped.set()

    task = asyncio.create_task(StudentWorker(jobs, BlockingExecutor(), "native").process_one())
    for _ in range(100):
        if started.is_set():
            break
        await asyncio.sleep(0.01)
    assert started.is_set()
    await jobs.cancel(scope.user, scope.project, job.id)
    assert await task and stopped.is_set()
    assert (await jobs.get(scope.user, scope.project, job.id)).state == "cancelled"


async def test_api_upload_learning_guide_quiz_with_mock_provider(client, app, fake_anthropic):
    response = await client.post("/api/student/uploads?filename=book.pdf", content=DATA)
    assert response.status_code == 201, response.text
    job = response.json()
    jobs = StudentIngestion(app.state.services.db)
    lease = await jobs.claim("fixture")
    await jobs.publish_extraction(lease, extracted())
    doc = job["document_id"]
    structure = (await client.get(f"/api/student/documents/{doc}/structure")).json()
    assert structure["sections"][1]["page"] == 2
    fake_anthropic.reply = "Fotosintez quyosh energiyasini saqlaydi [1]."
    for kind in ("answer", "study_guide", "summary"):
        result = await client.post(
            f"/api/student/documents/{doc}/learn", json={"kind": kind, "question": "Fotosintez"}
        )
        assert result.status_code == 200, result.text
        assert result.json()["citations"] and result.json()["generated"] is True
    fake_anthropic.reply = json.dumps(
        {
            "items": [
                {
                    "question": "Nima saqlanadi?",
                    "choices": ["Quyosh energiyasi", "Hech narsa"],
                    "answer": 0,
                    "explanation": "Quyosh energiyasi [1].",
                    "source": 1,
                }
            ]
        }
    )
    quiz = await client.post(f"/api/student/documents/{doc}/learn", json={"kind": "quiz"})
    assert quiz.status_code == 200 and quiz.json()["quiz"]["items"][0]["answer"] == 0
    for unverified in ("Uydirma [999].", "Claim [1][1234]", "Claim [1][1,1234]", "No citation"):
        fake_anthropic.reply = unverified
        invalid = await client.post(f"/api/student/documents/{doc}/learn", json={"kind": "summary"})
        assert invalid.status_code == 502
    app.state.services.router.providers = {}
    offline = await client.post(f"/api/student/documents/{doc}/learn", json={"kind": "summary"})
    assert offline.status_code == 503 and "provider_unavailable" in offline.text


@pytest.mark.parametrize("name,data", [("a.exe", DATA), ("a.pdf", b"not pdf"), ("a.epub", b"")])
async def test_raw_api_rejects_invalid_inputs(client, name, data):
    result = await client.post("/api/student/uploads", params={"filename": name}, content=data)
    assert result.status_code == 422


async def test_busy_executor_does_not_exhaust_healthy_jobs(db):
    from tests.integration.test_document_jobs import make_available

    scope, jobs, job = await raw_queued(db)

    class BusyExecutor:
        def extract(self, data, format, *, cancelled):
            raise ExecutorError("executor_busy")

    worker = StudentWorker(jobs, BusyExecutor(), "competing")
    for _ in range(6):
        await make_available(db, job.id)
        assert await worker.process_one()
    current = await jobs.get(scope.user, scope.project, job.id)
    assert current.attempts == 0 and current.state == "queued"


@pytest.mark.parametrize("locked", ["job", "document"])
async def test_native_postgresql_claim_skips_contended_job_and_document(db, locked):
    import asyncio

    from ezo_api.db.models import DocumentJob, KnowledgeDocument

    if db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL SKIP LOCKED requires a real PostgreSQL server")
    scope, jobs, job_a = await raw_queued(db)
    job_b = await jobs.submit_raw(scope.user, scope.project, "b.pdf", DATA + b"second")
    model, row_id = (
        (DocumentJob, job_a.id) if locked == "job" else (KnowledgeDocument, job_a.document_id)
    )
    async with db.sessionmaker() as blocker:
        await blocker.execute(select(model).where(model.id == row_id).with_for_update())
        assert (await asyncio.wait_for(jobs.claim("other-worker"), timeout=2)).job_id == job_b.id
        assert await asyncio.wait_for(jobs.claim("third-worker"), timeout=2) is None
        await blocker.rollback()
    assert (await asyncio.wait_for(jobs.claim("unlocked"), timeout=2)).job_id == job_a.id


async def test_selected_chapter_is_bounded_and_semantic_index_works(client, app, fake_anthropic):
    response = await client.post("/api/student/uploads?filename=book.pdf", content=DATA)
    job = response.json()
    jobs = StudentIngestion(app.state.services.db)
    lease = await jobs.claim("fixture")
    await jobs.publish_extraction(lease, extracted())
    doc = job["document_id"]
    indexed = await client.post(f"/api/student/documents/{doc}/semantic-index")
    assert indexed.status_code == 200 and indexed.json()["indexed"] == 2
    fake_anthropic.reply = "Fotosintez [1]."
    chapter = await client.post(
        f"/api/student/documents/{doc}/learn",
        json={"kind": "summary", "section_start": TEXT.index("\n") + 2},
    )
    assert chapter.status_code == 200, chapter.text
    assert len(chapter.json()["citations"]) == 1
    assert chapter.json()["citations"][0]["extra"]["start"] == TEXT.index("\n") + 2
    invalid = await client.post(
        f"/api/student/documents/{doc}/learn", json={"kind": "summary", "section_start": 1}
    )
    assert invalid.status_code == 404


async def test_learning_rejects_foreign_user_and_mutated_citation_offsets(client, app):
    from ezo_api.student.learning import LearningRequest, learn

    jobs = StudentIngestion(app.state.services.db)
    created = (await client.post("/api/student/uploads?filename=book.pdf", content=DATA)).json()
    lease = await jobs.claim("fixture")
    await jobs.publish_extraction(lease, extracted())
    other = await seed(app.state.services.db)
    async with app.state.services.db.sessionmaker() as session:
        with pytest.raises(JobError) as error:
            await learn(
                app.state.services,
                session,
                other.user,
                uuid.UUID(created["document_id"]),
                LearningRequest(kind="summary"),
            )
        assert error.value.status == 404
    async with app.state.services.db.sessionmaker() as session:
        chunks = (
            await session.scalars(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == uuid.UUID(created["document_id"])
                )
            )
        ).all()
        for chunk in chunks:
            chunk.meta = {**chunk.meta, "start": 1, "end": 2}
        await session.commit()
    response = await client.post(
        f"/api/student/documents/{created['document_id']}/learn", json={"kind": "summary"}
    )
    assert response.status_code == 200 and response.json()["status"] == "insufficient_evidence"


@pytest.mark.parametrize(
    "code", ["cleanup_failed", "isolation_unavailable", "executor_slot_conflict"]
)
async def test_fatal_executor_failure_stops_worker_without_failing_healthy_input(db, code):
    import asyncio

    scope, jobs, job = await raw_queued(db)

    class BrokenExecutor:
        calls = 0

        def extract(self, data, format, *, cancelled):
            self.calls += 1
            raise ExecutorError(code)

    executor = BrokenExecutor()
    with pytest.raises(ExecutorError) as error:
        await asyncio.wait_for(
            StudentWorker(jobs, executor, "fatal-worker").run(asyncio.Event()), timeout=5
        )
    assert error.value.code == code and executor.calls == 1
    current = await jobs.get(scope.user, scope.project, job.id)
    assert current.state == ("running" if code == "cleanup_failed" else "queued")
    assert current.attempts == (1 if code == "cleanup_failed" else 0)
    assert current.error_code is None
    with pytest.raises(JobError):
        await jobs.result(scope.user, scope.project, job.id)


async def test_legacy_ingestion_recovery_cannot_consume_student_native_sources(client, app):
    created = (await client.post("/api/student/uploads?filename=book.pdf", content=DATA)).json()
    # A real API restart invokes this legacy recovery method. Student jobs must
    # remain exclusive to their fenced worker, including after publication.
    assert await app.state.services.ingestion.resume_unfinished() == 0
    async with app.state.services.db.sessionmaker() as session:
        doc = await app.state.services.knowledge.ingest(session, uuid.UUID(created["document_id"]))
        assert doc.status == "queued" and doc.error is None
    response = await client.post(f"/api/knowledge/documents/{created['document_id']}/reindex")
    assert response.status_code == 409 and response.json()["error"]["code"] == "student_managed"
    jobs = StudentIngestion(app.state.services.db)
    lease = await jobs.claim("native")
    await jobs.publish_extraction(lease, extracted())
    async with app.state.services.db.sessionmaker() as session:
        doc = await app.state.services.knowledge.ingest(session, uuid.UUID(created["document_id"]))
        assert doc.status == "indexed" and doc.chunk_count == 2
