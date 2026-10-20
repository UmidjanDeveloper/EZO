"""Durability, real SQL contention, fencing and exact revision/tenant publication."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta

import pytest
from sqlalchemy import event, func, select, update

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DocumentJob,
    DocumentJobPublication,
    DocumentRevision,
    KnowledgeDocument,
    KnowledgeSource,
    Project,
    User,
)
from ezo_api.db.session import Database
from ezo_api.knowledge.jobs.service import DocumentJobs, JobError
from ezo_api.schemas.document_jobs import CitationSpan

TEXT = "O‘zbekiston 🙂 — Ўзбекистон\n\nLearning is personal."
SPANS = [CitationSpan(start=0, end=TEXT.index("\n"))]


@dataclass
class Scope:
    user: uuid.UUID
    project: uuid.UUID
    document: uuid.UUID
    revision: uuid.UUID


async def seed(db: Database, *, user_id: uuid.UUID | None = None) -> Scope:
    async with db.sessionmaker() as session:
        if user_id is None:
            user = User(email=f"{uuid.uuid4()}@example.test", display_name="Learner")
            session.add(user)
            await session.flush()
            user_id = user.id
        project = Project(user_id=user_id, name="Private course")
        session.add(project)
        await session.flush()
        source = KnowledgeSource(
            user_id=user_id, project_id=project.id, name="Book", source_type="upload"
        )
        session.add(source)
        await session.flush()
        doc = KnowledgeDocument(
            user_id=user_id,
            source_id=source.id,
            project_id=project.id,
            title="Book",
            mime_type="text/plain",
            content_hash="a" * 64,
        )
        session.add(doc)
        await session.flush()
        revision = DocumentRevision(
            document_id=doc.id, revision_number=1, content_hash="a" * 64, raw_text=TEXT
        )
        session.add(revision)
        await session.flush()
        doc.current_revision_id = revision.id
        await session.commit()
        return Scope(user_id, project.id, doc.id, revision.id)


@pytest.fixture
async def db(database_url):
    database = Database(database_url)
    yield database
    await database.dispose()


async def queued(db):
    scope = await seed(db)
    jobs = DocumentJobs(db)
    job = await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    return scope, jobs, job


async def expire(db, lease):
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentJob)
            .where(DocumentJob.id == lease.job_id)
            .values(lease_expires_at=utcnow() - timedelta(seconds=10))
        )
        await session.commit()


async def make_available(db, job_id):
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentJob)
            .where(DocumentJob.id == job_id)
            .values(available_at=utcnow() - timedelta(seconds=10))
        )
        await session.commit()


async def test_job_survives_engine_and_service_restart(database_url):
    first = Database(database_url)
    scope, jobs, job = await queued(first)
    lease = await jobs.claim("before-restart")
    assert lease is not None
    await first.dispose()
    second = Database(database_url)
    try:
        jobs = DocumentJobs(second)
        assert (await jobs.get(scope.user, scope.project, job.id)).state == "running"
        assert await jobs.claim("new-process") is None
        await expire(second, lease)
        recovered = await jobs.claim("new-process")
        assert recovered is not None and recovered.attempt == 2
        result = await jobs.publish(recovered, TEXT, SPANS)
        assert (await jobs.get(scope.user, scope.project, job.id)).state == "completed"
        await second.dispose()
        third = Database(database_url)
        try:
            assert (
                await DocumentJobs(third).result(scope.user, scope.project, job.id)
            ).id == result.id
        finally:
            await third.dispose()
    finally:
        await second.dispose()


async def test_two_independent_claimers_only_one_active_lease(db):
    _, _, job = await queued(db)
    first, second = await asyncio.gather(
        DocumentJobs(db).claim("one"), DocumentJobs(db).claim("two")
    )
    winners = [lease for lease in [first, second] if lease is not None]
    assert len(winners) == 1 and winners[0].job_id == job.id and winners[0].attempt == 1


async def test_postgresql_claim_skips_a_locked_job(db):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL SKIP LOCKED requires real PostgreSQL")
    _, jobs, job = await queued(db)
    async with db.sessionmaker() as blocker:
        await blocker.execute(select(DocumentJob).where(DocumentJob.id == job.id).with_for_update())
        # Would block if SKIP LOCKED was omitted; no fake SQL compiler assertions.
        assert await asyncio.wait_for(jobs.claim("independent-worker"), timeout=2) is None
        await blocker.rollback()
    assert (await jobs.claim("after-unlock")).job_id == job.id


async def test_expired_lease_reclaimed_and_old_worker_fenced(db):
    _, jobs, job = await queued(db)
    old = await jobs.claim("old")
    await expire(db, old)
    new = await jobs.claim("replacement")
    assert new.token != old.token and new.attempt == old.attempt + 1
    with pytest.raises(JobError, match="lease"):
        await jobs.publish(old, TEXT, SPANS)
    publication = await jobs.publish(new, TEXT, SPANS)
    assert publication.job_id == job.id


@pytest.mark.parametrize("operation", ["publish", "heartbeat", "fail"])
async def test_expiry_itself_revokes_rights_without_reclaim(db, operation):
    _, jobs, _ = await queued(db)
    lease = await jobs.claim("worker")
    await expire(db, lease)
    with pytest.raises(JobError) as error:
        if operation == "publish":
            await jobs.publish(lease, TEXT, SPANS)
        elif operation == "heartbeat":
            await jobs.heartbeat(lease)
        else:
            await jobs.fail(lease, "transient")
    assert error.value.code == "lease_lost"


@pytest.mark.parametrize("running", [False, True])
async def test_cancellation_is_durable_and_revokes_publication(db, running):
    scope, jobs, job = await queued(db)
    lease = await jobs.claim("worker") if running else None
    assert (await jobs.cancel(scope.user, scope.project, job.id)).state == "cancelled"
    assert (await jobs.cancel(scope.user, scope.project, job.id)).state == "cancelled"
    assert await DocumentJobs(db).claim("restart") is None
    if lease:
        with pytest.raises(JobError):
            await jobs.publish(lease, TEXT, SPANS)
    async with db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentJobPublication)) == 0


async def test_retry_backoff_and_attempt_limit(db):
    scope, jobs, job = await queued(db)
    for attempt in range(1, 4):
        lease = await jobs.claim("worker")
        assert lease.attempt == attempt
        await jobs.fail(lease, "transient")
        assert await jobs.claim("too-early") is None
        await make_available(db, job.id)
    failed = await jobs.get(scope.user, scope.project, job.id)
    assert failed.state == "failed" and failed.attempts == 3
    assert await jobs.claim("fourth-attempt") is None
    assert failed.error_code == "transient"


async def test_crashes_also_exhaust_the_attempt_limit(db):
    scope, jobs, job = await queued(db)
    for attempt in range(1, 4):
        lease = await jobs.claim("crashing-worker")
        assert lease.attempt == attempt
        await expire(db, lease)
    assert await jobs.claim("fourth") is None
    state = await jobs.get(scope.user, scope.project, job.id)
    assert state.state == "failed" and state.error_code == "attempts_exhausted"


async def test_completion_is_idempotent_and_conflicting_republication_rejected(db):
    scope, jobs, job = await queued(db)
    assert (
        await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    ).id == job.id
    lease = await jobs.claim("worker")
    first, repeated = await asyncio.gather(
        jobs.publish(lease, TEXT, SPANS), DocumentJobs(db).publish(lease, TEXT, SPANS)
    )
    assert first.id == repeated.id
    with pytest.raises(JobError) as error:
        await jobs.publish(lease, TEXT, [])
    assert error.value.code == "publication_conflict"
    with pytest.raises(JobError):
        await jobs.cancel(scope.user, scope.project, job.id)
    async with db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentJobPublication)) == 1
        doc = await session.get(KnowledgeDocument, scope.document)
        assert doc.current_revision_id == scope.revision  # K1/K2 current pointer never changed


async def test_publication_and_completed_state_roll_back_together(db):
    scope, jobs, job = await queued(db)
    lease = await jobs.claim("worker")

    def fail_write(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO document_job_publications"):
            raise RuntimeError("simulated database write failure")

    event.listen(db.engine.sync_engine, "before_cursor_execute", fail_write)
    try:
        with pytest.raises(RuntimeError):
            await jobs.publish(lease, TEXT, SPANS)
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", fail_write)
    assert (await jobs.get(scope.user, scope.project, job.id)).state == "running"
    async with db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentJobPublication)) == 0
    assert (await jobs.publish(lease, TEXT, SPANS)).job_id == job.id


async def test_user_project_document_and_revision_scope_cannot_be_substituted(db):
    scope, jobs, job = await queued(db)
    other_workspace = await seed(db, user_id=scope.user)
    outsider = await seed(db)
    for user, project in [
        (outsider.user, scope.project),
        (scope.user, other_workspace.project),
        (scope.user, None),
    ]:
        for method in [jobs.get, jobs.cancel, jobs.result]:
            with pytest.raises(JobError) as error:
                await method(user, project, job.id)
            assert error.value.status == 404
        with pytest.raises(JobError):
            await jobs.enqueue(user, project, scope.document, scope.revision)
    with pytest.raises(JobError):
        await jobs.enqueue(scope.user, scope.project, scope.document, other_workspace.revision)


@pytest.mark.parametrize(
    "value,spans,code",
    [
        (TEXT, [CitationSpan(start=0, end=len(TEXT) + 1)], "invalid_offsets"),
        (TEXT, [CitationSpan(start=2, end=5), CitationSpan(start=1, end=2)], "invalid_offsets"),
        (TEXT + "\r\n", SPANS, "invalid_text"),
        ("Different normalized text", [], "revision_conflict"),
        ("x" * 2_000_001, [], "resource_limit"),
    ],
    ids=["bounds", "unordered", "normalization", "revision", "size"],
)
async def test_publication_validates_exact_text_and_citation_offsets(db, value, spans, code):
    _, jobs, _ = await queued(db)
    lease = await jobs.claim("worker")
    with pytest.raises(JobError) as error:
        await jobs.publish(lease, value, spans)
    assert error.value.code == code


async def test_published_text_and_offsets_remain_immutable_across_new_source_revision(db):
    scope, jobs, job = await queued(db)
    lease = await jobs.claim("worker")
    publication = await jobs.publish(lease, TEXT, SPANS)
    async with db.sessionmaker() as session:
        new = DocumentRevision(
            document_id=scope.document,
            revision_number=2,
            content_hash="b" * 64,
            raw_text="A new edition with different locations.",
        )
        session.add(new)
        await session.flush()
        doc = await session.get(KnowledgeDocument, scope.document)
        doc.current_revision_id = new.id
        await session.commit()
    old = await jobs.result(scope.user, scope.project, job.id)
    assert old.id == publication.id and old.normalized_text == TEXT
    assert (
        old.normalized_text[old.spans[0]["start"] : old.spans[0]["end"]]
        == "O‘zbekiston 🙂 — Ўзбекистон"
    )


async def test_heartbeat_extends_active_lease(db):
    _, jobs, job = await queued(db)
    lease = await jobs.claim("worker")
    soon = utcnow() + timedelta(seconds=5)
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentJob).where(DocumentJob.id == job.id).values(lease_expires_at=soon)
        )
        await session.commit()
    await jobs.heartbeat(lease)
    async with db.sessionmaker() as session:
        assert (await session.get(DocumentJob, job.id)).lease_expires_at > soon + timedelta(
            seconds=30
        )


async def test_sqlite_fallback_uses_database_lock_across_service_instances(db):
    if db.engine.dialect.name != "sqlite":
        pytest.skip("SQLite-only single-worker development contract")
    _, _, job = await queued(db)
    a, b = await asyncio.gather(DocumentJobs(db).claim("one"), DocumentJobs(db).claim("two"))
    assert sum(lease is not None for lease in (a, b)) == 1
    assert (a or b).job_id == job.id


async def test_cancel_racing_publication_has_one_atomic_outcome(db):
    scope, jobs, job = await queued(db)
    lease = await jobs.claim("worker")
    outcomes = await asyncio.gather(
        jobs.cancel(scope.user, scope.project, job.id),
        jobs.publish(lease, TEXT, SPANS),
        return_exceptions=True,
    )
    state = await jobs.get(scope.user, scope.project, job.id)
    async with db.sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(DocumentJobPublication))
    assert (state.state, count) in [("cancelled", 0), ("completed", 1)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(failures) == 1 and isinstance(failures[0], JobError)


async def test_error_categories_do_not_accept_raw_exception_or_secret_strings(db):
    scope, jobs, job = await queued(db)
    lease = await jobs.claim("worker")
    with pytest.raises(ValueError):
        await jobs.fail(lease, "Bearer sensitive-exception-detail")
    await jobs.fail(lease, "internal_error")
    failed = await jobs.get(scope.user, scope.project, job.id)
    assert failed.error_code == "internal_error"
    assert "sensitive" not in failed.error_message and len(failed.error_message) <= 200


async def test_api_enqueue_get_cancel_never_starts_a_parser(client, app, monkeypatch):
    from tests.integration.test_knowledge_api import upload

    uploaded = (await upload(client, "student.txt", TEXT.encode())).json()["document"]
    detail = (await client.get("/api/knowledge/documents/" + uploaded["id"])).json()
    revision = detail["revisions"][0]["id"]

    def forbidden(*args, **kwargs):
        pytest.fail("Job control plane must not parse or submit to legacy runner")

    monkeypatch.setattr(app.state.services.ingestion, "submit", forbidden)
    response = await client.post(
        "/api/knowledge/documents/" + uploaded["id"] + "/jobs", json={"revision_id": revision}
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["state"] == "queued" and "lease_token" not in job and "worker_id" not in job
    assert (await client.get("/api/knowledge/document-jobs/" + job["id"])).status_code == 200
    assert (
        await client.get("/api/knowledge/document-jobs/" + job["id"] + "/result")
    ).status_code == 409
    duplicate = await client.post(
        "/api/knowledge/documents/" + uploaded["id"] + "/jobs", json={"revision_id": revision}
    )
    assert duplicate.json()["id"] == job["id"]
    forbidden_body = await client.post(
        "/api/knowledge/documents/" + uploaded["id"] + "/jobs",
        json={"revision_id": revision, "command": "untrusted"},
    )
    assert forbidden_body.status_code == 422
    cancelled = await client.post("/api/knowledge/document-jobs/" + job["id"] + "/cancel")
    assert cancelled.json()["state"] == "cancelled"


async def test_api_project_scope_and_bounded_result(client, app):
    from tests.integration.test_knowledge_api import upload

    project = (await client.post("/api/projects", json={"name": "Course"})).json()
    uploaded = (await upload(client, "lesson.txt", TEXT.encode(), project_id=project["id"])).json()[
        "document"
    ]
    revision = (await client.get("/api/knowledge/documents/" + uploaded["id"])).json()["revisions"][
        0
    ]["id"]
    url = "/api/knowledge/documents/" + uploaded["id"] + "/jobs"
    assert (await client.post(url, json={"revision_id": revision})).status_code == 404
    job = (
        await client.post(url, json={"revision_id": revision, "project_id": project["id"]})
    ).json()
    base = "/api/knowledge/document-jobs/" + job["id"]
    assert (await client.get(base)).status_code == 404
    assert (await client.post(base + "/cancel")).status_code == 404
    assert (await client.get(base, params={"project_id": str(uuid.uuid4())})).status_code == 404
    jobs = DocumentJobs(app.state.services.db)
    lease = await jobs.claim("trusted-test-worker")
    await jobs.publish(lease, TEXT, SPANS)
    result = await client.get(
        base + "/result", params={"project_id": project["id"], "offset": 2, "limit": 4}
    )
    assert result.status_code == 200, result.text
    assert (
        result.json()["text"] == TEXT[2:6] and result.json()["offset_unit"] == "unicode_codepoints"
    )
    assert result.json()["input_revision_id"] == revision
    assert (
        await client.get(base + "/result", params={"project_id": project["id"], "limit": 8001})
    ).status_code == 422


async def test_configured_attempt_budget_is_pinned_at_enqueue(db):
    scope = await seed(db)
    jobs = DocumentJobs(db, max_attempts=1)
    job = await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    assert job.max_attempts == 1
    lease = await jobs.claim("worker")
    await jobs.fail(lease, "transient")
    assert (await jobs.get(scope.user, scope.project, job.id)).state == "failed"
    assert (
        await DocumentJobs(db, max_attempts=5).enqueue(
            scope.user, scope.project, scope.document, scope.revision
        )
    ).max_attempts == 1
    assert await jobs.claim("retry") is None


@pytest.mark.parametrize(
    "options",
    [{"lease_seconds": 0}, {"lease_seconds": 301}, {"max_attempts": 0}, {"max_attempts": 6}],
)
def test_worker_configuration_is_bounded(options):
    with pytest.raises(ValueError):
        DocumentJobs(None, **options)


async def test_deleted_document_cannot_receive_late_publication(db):
    scope, jobs, job = await queued(db)
    lease = await jobs.claim("worker")
    async with db.sessionmaker() as session:
        document = await session.get(KnowledgeDocument, scope.document)
        await session.delete(document)
        await session.commit()
    with pytest.raises(JobError) as error:
        await jobs.publish(lease, TEXT, SPANS)
    assert error.value.status == 404
    async with db.sessionmaker() as session:
        assert await session.get(DocumentJob, job.id) is None
        assert await session.scalar(select(func.count()).select_from(DocumentJobPublication)) == 0


async def test_claim_rejects_revision_scope_corruption(db):
    _, jobs, job = await queued(db)
    outsider = await seed(db)
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentJob)
            .where(DocumentJob.id == job.id)
            .values(input_revision_id=outsider.revision)
        )
        await session.commit()
    assert await jobs.claim("worker") is None


async def test_job_api_checks_auth_before_consuming_body(database_url):
    from httpx import ASGITransport, AsyncClient

    from ezo_api.main import create_app
    from tests.conftest import make_settings

    application = create_app(
        make_settings(database_url, EZO_AUTH_MODE="token", EZO_API_TOKEN="local-job-test-only")
    )

    async def unread():
        pytest.fail("Unauthenticated job request consumed the body")
        yield b"{}"

    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as ac:
            response = await ac.post(
                "/api/knowledge/documents/" + str(uuid.uuid4()) + "/jobs",
                content=unread(),
                headers={"content-type": "application/json"},
            )
            assert response.status_code == 401
    finally:
        await application.state.services.db.dispose()


async def test_mutating_pinned_source_text_is_detected_before_publication(db):
    scope, jobs, _job = await queued(db)
    lease = await jobs.claim("worker")
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentRevision)
            .where(DocumentRevision.id == scope.revision)
            .values(raw_text="Changed but still normalized text.")
        )
        await session.commit()
    with pytest.raises(JobError) as error:
        await jobs.publish(lease, "Changed but still normalized text.", [])
    assert error.value.code == "revision_conflict"
    with pytest.raises(JobError):
        await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)


async def test_processor_version_upgrade_creates_a_new_immutable_publication(db, monkeypatch):
    from ezo_api.knowledge.jobs import service

    scope, jobs, old_job = await queued(db)
    old_lease = await jobs.claim("v1-worker")
    old_result = await jobs.publish(old_lease, TEXT, SPANS)
    monkeypatch.setattr(service, "PARSER_VERSION", "stored-normalized-text/v2-test")
    new_job = await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    assert new_job.id != old_job.id
    new_lease = await jobs.claim("v2-worker")
    new_result = await jobs.publish(new_lease, TEXT, [])
    assert new_result.id != old_result.id
    unchanged = await jobs.result(scope.user, scope.project, old_job.id)
    assert (
        unchanged.spans == old_result.spans
        and unchanged.parser_version == old_result.parser_version
    )


async def test_oversized_source_is_rejected_before_materializing_revision_text(db):
    scope = await seed(db)
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentRevision)
            .where(DocumentRevision.id == scope.revision)
            .values(raw_text="x" * 2_000_001)
        )
        await session.commit()

    # An ORM load guard proves the oversized body never reaches the Python object.
    def no_oversized_load(instance, context):
        if instance.id == scope.revision:
            pytest.fail("Oversized source was materialized before checking its SQL budget")

    event.listen(DocumentRevision, "load", no_oversized_load)
    try:
        with pytest.raises(JobError) as error:
            await DocumentJobs(db).enqueue(
                scope.user, scope.project, scope.document, scope.revision
            )
        assert error.value.code == "resource_limit"
    finally:
        event.remove(DocumentRevision, "load", no_oversized_load)


async def test_claim_skips_project_owner_mismatch_without_poisoning_queue(db):
    stale, jobs, stale_job = await queued(db)
    healthy, _, healthy_job = await queued(db)
    # Individual FKs remain valid: a maintenance/ownership change can leave
    # legacy document/job ownership inconsistent with the project's current owner.
    async with db.sessionmaker() as session:
        await session.execute(
            update(Project).where(Project.id == stale.project).values(user_id=healthy.user)
        )
        await session.commit()
    lease = await jobs.claim("healthy-worker")
    assert lease is not None and lease.job_id == healthy_job.id
    assert await jobs.claim("repeat-poll") is None
    async with db.sessionmaker() as session:
        untouched = await session.get(DocumentJob, stale_job.id)
        assert untouched.state == "queued" and untouched.attempts == 0
    # Repairing ownership makes the original healthy input eligible again.
    async with db.sessionmaker() as session:
        await session.execute(
            update(Project).where(Project.id == stale.project).values(user_id=stale.user)
        )
        await session.commit()
    assert (await jobs.claim("after-repair")).job_id == stale_job.id


@pytest.mark.parametrize("locked_model", [DocumentJob, KnowledgeDocument], ids=["job", "document"])
async def test_postgresql_claims_second_job_while_first_row_locked(db, locked_model):
    if db.engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL row contention; SQLite cannot emulate SKIP LOCKED")
    first, jobs, job_a = await queued(db)
    _, _, job_b = await queued(db)
    async with db.sessionmaker() as blocker:
        row_id = job_a.id if locked_model is DocumentJob else first.document
        await blocker.execute(
            select(locked_model).where(locked_model.id == row_id).with_for_update()
        )
        lease_b = await asyncio.wait_for(jobs.claim("worker-b"), timeout=2)
        assert lease_b is not None and lease_b.job_id == job_b.id
        assert await asyncio.wait_for(jobs.claim("still-locked"), timeout=2) is None
        await blocker.rollback()
    lease_a = await asyncio.wait_for(jobs.claim("after-unlock"), timeout=2)
    assert lease_a is not None and lease_a.job_id == job_a.id
    assert lease_a.attempt == lease_b.attempt == 1


async def test_result_api_slices_in_sql_without_loading_publication(client, app):
    from tests.integration.test_knowledge_api import upload

    value = "🙂Ўé" * 100_000
    uploaded = (await upload(client, "large.txt", value.encode())).json()["document"]
    revision = (await client.get("/api/knowledge/documents/" + uploaded["id"])).json()["revisions"][
        0
    ]["id"]
    job = (
        await client.post(
            "/api/knowledge/documents/" + uploaded["id"] + "/jobs", json={"revision_id": revision}
        )
    ).json()
    jobs = DocumentJobs(app.state.services.db)
    lease = await jobs.claim("test-worker")
    publication = await jobs.publish(
        lease, value, [CitationSpan(start=1, end=12), CitationSpan(start=20, end=30)]
    )

    def no_full_load(instance, context):
        pytest.fail("Paginated result materialized the entire publication")

    statements = []

    def record_sql(conn, cursor, statement, parameters, context, many):
        if "document_job_publications" in statement:
            statements.append(statement)

    event.listen(app.state.services.db.engine.sync_engine, "before_cursor_execute", record_sql)
    event.listen(DocumentJobPublication, "load", no_full_load)
    try:
        response = await client.get(
            "/api/knowledge/document-jobs/" + job["id"] + "/result",
            params={"offset": 5, "limit": 8},
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["text"] == value[5:13] and page["total_chars"] == len(value)
        assert page["spans"] == [{"start": 1, "end": 12}]
        assert page["text_sha256"] == publication.text_sha256
        assert len(statements) == 1 and "substr(" in statements[0].lower()
    finally:
        event.remove(DocumentJobPublication, "load", no_full_load)
        event.remove(app.state.services.db.engine.sync_engine, "before_cursor_execute", record_sql)


@pytest.mark.parametrize(
    "offset,limit,expected_spans",
    [
        (0, 1, []),
        (1, 1, [(1, 5)]),
        (4, 2, [(1, 5), (5, 8)]),
        (5, 1, [(5, 8)]),
        (8, 1, []),
        (9, 8, []),
        (10**30, 8, []),
    ],
)
async def test_result_page_unicode_boundaries_and_out_of_range(db, offset, limit, expected_spans):
    scope = await seed(db)
    value = "🙂ЎéabcXYZ"
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentRevision)
            .where(DocumentRevision.id == scope.revision)
            .values(raw_text=value)
        )
        await session.commit()
    jobs = DocumentJobs(db)
    job = await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    publication = await jobs.publish(
        await jobs.claim("worker"),
        value,
        [CitationSpan(start=1, end=5), CitationSpan(start=5, end=8)],
    )
    page = await jobs.result_page(scope.user, scope.project, job.id, offset=offset, limit=limit)
    assert page.text == value[offset : offset + limit]
    assert page.offset == offset and page.total_chars == len(value)
    assert [(s.start, s.end) for s in page.spans] == expected_spans
    assert page.text_sha256 == publication.text_sha256
    assert page.input_revision_id == scope.revision


async def test_result_page_empty_publication_and_authorization_before_read(db):
    scope = await seed(db)
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentRevision)
            .where(DocumentRevision.id == scope.revision)
            .values(raw_text="")
        )
        await session.commit()
    jobs = DocumentJobs(db)
    job = await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    with pytest.raises(JobError) as unavailable:
        await jobs.result_page(scope.user, scope.project, job.id)
    assert unavailable.value.code == "result_unavailable"
    await jobs.publish(await jobs.claim("worker"), "", [])
    page = await jobs.result_page(scope.user, scope.project, job.id)
    assert page.text == "" and page.spans == [] and page.total_chars == 0
    outsider = await seed(db)

    def forbid_publication_query(conn, cursor, statement, parameters, context, many):
        assert "document_job_publications" not in statement

    event.listen(db.engine.sync_engine, "before_cursor_execute", forbid_publication_query)
    try:
        for user, project in [
            (outsider.user, scope.project),
            (scope.user, None),
            (scope.user, outsider.project),
        ]:
            with pytest.raises(JobError) as error:
                await jobs.result_page(user, project, job.id)
            assert error.value.status == 404
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", forbid_publication_query)


async def test_result_page_filters_maximum_citation_payload(db):
    scope = await seed(db)
    value = "x" * 2000
    async with db.sessionmaker() as session:
        await session.execute(
            update(DocumentRevision)
            .where(DocumentRevision.id == scope.revision)
            .values(raw_text=value)
        )
        await session.commit()
    jobs = DocumentJobs(db)
    job = await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    spans = [CitationSpan(start=i, end=i + 1) for i in range(0, 2000, 2)]
    await jobs.publish(await jobs.claim("worker"), value, spans)
    page = await jobs.result_page(scope.user, scope.project, job.id, offset=1000, limit=1)
    assert page.spans == [CitationSpan(start=1000, end=1001)]
    for offset, limit in [(-1, 1), (0, 0), (0, 8001)]:
        with pytest.raises(JobError) as error:
            await jobs.result_page(scope.user, scope.project, job.id, offset=offset, limit=limit)
        assert error.value.status == 422


@pytest.mark.parametrize("terminal", ["failed", "cancelled"])
async def test_terminal_enqueue_and_cancel_preserve_state_and_budget(db, terminal):
    scope, jobs, job = await queued(db)
    lease = await jobs.claim("worker")
    if terminal == "failed":
        await jobs.fail(lease, "invalid_input")
    else:
        await jobs.cancel(scope.user, scope.project, job.id)
    original = await jobs.get(scope.user, scope.project, job.id)
    cancelled = await jobs.cancel(scope.user, scope.project, job.id)
    duplicate = await jobs.enqueue(scope.user, scope.project, scope.document, scope.revision)
    assert cancelled.state == duplicate.state == terminal
    assert duplicate.id == job.id and duplicate.attempts == original.attempts == 1
    assert duplicate.max_attempts == original.max_attempts
    assert cancelled.error_code == duplicate.error_code == original.error_code
    assert await jobs.claim("no-revival") is None
    with pytest.raises(JobError):
        await jobs.publish(lease, TEXT, SPANS)


@pytest.mark.parametrize("worker_id", ["", "x" * 81, "worker space", "worker\n", "ў-worker", "a/b"])
async def test_invalid_worker_identifier_cannot_consume_an_attempt(db, worker_id):
    scope, jobs, job = await queued(db)
    with pytest.raises(ValueError):
        await jobs.claim(worker_id)
    untouched = await jobs.get(scope.user, scope.project, job.id)
    assert untouched.state == "queued" and untouched.attempts == 0
