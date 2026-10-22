"""Actual source provenance, tenant negatives, fencing and durable recall history."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, update

from ezo_api.db.models import KnowledgeChunk, KnowledgeDocument, StudyCard, StudyReview
from ezo_api.student.ingestion import StudentIngestion
from ezo_api.student.study import ReviewIn, review_card
from tests.integration.test_document_jobs import seed
from tests.integration.test_student_v1 import DATA, TEXT, extracted


async def source(client, app):
    result = await client.post("/api/student/uploads?filename=study.pdf", content=DATA)
    assert result.status_code == 201, result.text
    job = result.json()
    jobs = StudentIngestion(app.state.services.db)
    await jobs.publish_extraction(await jobs.claim("test"), extracted())
    async with app.state.services.db.sessionmaker() as session:
        chunk = await session.scalar(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == uuid.UUID(job["document_id"]))
            .order_by(KnowledgeChunk.chunk_index)
        )
        return {
            "document_id": job["document_id"],
            "revision_id": str(chunk.revision_id),
            "chunk_id": str(chunk.id),
            "quote_start": 0,
            "quote_end": chunk.meta["end"],
            "front": "Nima?",
            "back": "O‘zbekiston 🙂",
        }, chunk.user_id


async def card(client, app):
    body, user = await source(client, app)
    r = await client.post("/api/student/cards", json=body)
    assert r.status_code == 201, r.text
    return r.json(), user


async def test_quote_offsets_recall_idempotency_and_progress(client, app):
    c, _ = await card(client, app)
    assert c["quote"] == TEXT[: c["quote_end"]]
    assert c["offset_unit"] == "unicode_codepoints"
    initial = (await client.get("/api/student/progress")).json()
    assert initial["due_cards"] == 1 and initial["review_events"] == 0
    body = {"event_id": str(uuid.uuid4()), "expected_version": 0, "rating": "good"}
    r = await client.post(f"/api/student/cards/{c['id']}/review", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["interval_days"] == 1
    replay = await client.post(f"/api/student/cards/{c['id']}/review", json=body)
    assert replay.json() == r.json()
    changed = await client.post(
        f"/api/student/cards/{c['id']}/review", json={**body, "rating": "easy"}
    )
    assert changed.status_code == 409
    stale = await client.post(
        f"/api/student/cards/{c['id']}/review", json={**body, "event_id": str(uuid.uuid4())}
    )
    assert stale.status_code == 409
    p = (await client.get("/api/student/progress")).json()
    assert p["review_events"] == p["reviewed_cards"] == 1
    assert p["due_cards"] == 0 and p["assessment"] == "self_reported_recall"
    assert (await client.get("/api/student/cards?due_only=true")).json() == []
    assert (await client.get("/api/student/cards?offset=100")).json() == []
    assert (await client.get("/api/student/cards?limit=101")).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"quote_start": 0, "quote_end": 2001},
        {"quote_end": 0},
        {"quote_start": 10, "quote_end": 9},
        {"chunk_id": str(uuid.uuid4())},
        {"front": " "},
        {"back": "x" * 2001},
        {"execute": "anything"},
    ],
)
async def test_invalid_or_unbounded_cards_rejected(client, app, change):
    body, _ = await source(client, app)
    r = await client.post("/api/student/cards", json={**body, **change})
    assert r.status_code == 422, r.text


async def test_exact_project_and_owner_scope(client, app):
    body, _ = await source(client, app)
    db = app.state.services.db
    foreign = await seed(db)
    r = await client.post("/api/student/cards", json={**body, "project_id": str(foreign.project)})
    assert r.status_code == 404
    c = (await client.post("/api/student/cards", json=body)).json()
    async with db.sessionmaker() as session:
        await session.execute(
            update(StudyCard).where(StudyCard.id == uuid.UUID(c["id"])).values(user_id=foreign.user)
        )
        await session.commit()
    assert (await client.get("/api/student/cards")).json() == []
    r = await client.post(
        f"/api/student/cards/{c['id']}/review",
        json={"event_id": str(uuid.uuid4()), "expected_version": 0, "rating": "good"},
    )
    assert r.status_code == 404
    assert (await client.delete(f"/api/student/cards/{c['id']}?confirm=true")).status_code == 404


async def test_source_invalidation_preserves_events_until_explicit_deletion(client, app):
    c, _ = await card(client, app)
    body = {"event_id": str(uuid.uuid4()), "expected_version": 0, "rating": "again"}
    path = f"/api/student/cards/{c['id']}"
    original = await client.post(path + "/review", json=body)
    assert original.status_code == 200 and original.json()["interval_days"] == 0
    async with app.state.services.db.sessionmaker() as session:
        await session.execute(
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == uuid.UUID(c["document_id"]))
            .values(current_revision_id=None)
        )
        await session.commit()
    assert (await client.get("/api/student/cards")).json() == []
    assert (await client.get("/api/student/progress")).json()["active_cards"] == 0
    assert (await client.post(path + "/review", json=body)).json() == original.json()
    new = await client.post(
        path + "/review", json={**body, "event_id": str(uuid.uuid4()), "expected_version": 1}
    )
    assert new.status_code == 409
    assert (await client.delete(path)).status_code == 409
    assert (await client.delete(path + "?confirm=true")).status_code == 204
    async with app.state.services.db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(StudyReview)) == 0


async def test_postgres_concurrent_duplicate_is_exactly_once(client, app):
    if app.state.services.db.engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL document-lock serialization")
    c, user = await card(client, app)
    body = ReviewIn(event_id=uuid.uuid4(), expected_version=0, rating="easy")

    async def submit():
        async with app.state.services.db.sessionmaker() as session:
            return await review_card(session, user, uuid.UUID(c["id"]), body)

    results = await asyncio.gather(submit(), submit())
    assert results[0] == results[1] and results[0]["version"] == 1
    async with app.state.services.db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(StudyReview)) == 1


async def test_postgres_concurrent_card_deletion_returns_not_found(client, app):
    from sqlalchemy import delete, text

    if app.state.services.db.engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL concurrent deletion")
    c, _ = await card(client, app)
    db = app.state.services.db
    task = None
    async with db.sessionmaker() as blocker:
        await blocker.scalar(
            select(KnowledgeDocument.id)
            .where(KnowledgeDocument.id == uuid.UUID(c["document_id"]))
            .with_for_update()
        )
        try:
            task = asyncio.create_task(
                client.post(
                    f"/api/student/cards/{c['id']}/review",
                    json={"event_id": str(uuid.uuid4()), "expected_version": 0, "rating": "good"},
                )
            )
            async with db.sessionmaker() as observer:
                for _ in range(100):
                    waiting = await observer.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE "
                            "datname=current_database() AND pid<>pg_backend_pid() "
                            "AND wait_event_type='Lock' AND query ILIKE '%knowledge_documents%' "
                            "AND query ILIKE '%FOR UPDATE%')"
                        )
                    )
                    await observer.rollback()
                    if waiting:
                        break
                    await asyncio.sleep(0.01)
                assert waiting, "Review must reach the held document lock"
            async with db.sessionmaker() as deleting:
                await deleting.execute(delete(StudyCard).where(StudyCard.id == uuid.UUID(c["id"])))
                await deleting.commit()
        finally:
            await blocker.rollback()
        assert task is not None
        response = await asyncio.wait_for(task, 10)
    assert response.status_code == 404
