"""Real SQL/files/provider-fixture refresh, revocation, replay and crash boundaries."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from ezo_api.db.models import (
    AuditLog,
    DocumentRevision,
    KnowledgeDocument,
    LearnedSource,
    SourceRefreshBlob,
    SourceRefreshPolicy,
    SourceRefreshRun,
)
from ezo_api.knowledge.jobs.service import JobError
from ezo_api.learning.base import Budget, Limits
from ezo_api.learning.refresh import RefreshQueue
from ezo_api.learning.refresh_worker import RefreshWorker
from tests.integration.test_learning import learn
from tests.learning_web import DOCS, docs_site, page

pytest_plugins = ("tests.integration.test_learning",)


async def setup(api, learning_app, web):
    docs_site(web)
    source = await learn(api, f"{DOCS}/guide/")
    q = RefreshQueue(learning_app.state.services.db)
    worker = RefreshWorker(q, learning_app.state.services.learning.service)
    async with q.transaction(write=False) as session:
        user = (await session.get(LearnedSource, uuid.UUID(source["id"]))).user_id
    return source, user, q, worker


async def staged(q, worker):
    lease = await q.claim()
    assert lease is not None
    budget = Budget(Limits.model_validate(lease.input["limits"]))
    inspection = await worker.inspect(lease, budget)
    prepared = await worker.prepare(lease, inspection)
    return lease, budget, inspection, prepared


async def document_state(q, source_id):
    async with q.transaction(write=False) as session:
        source = await session.get(LearnedSource, source_id)
        rows = (
            await session.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.source_id == source.knowledge_source_id)
                .order_by(KnowledgeDocument.id)
            )
        ).all()
        return [(d.id, d.content_hash, d.current_revision_id, d.status) for d in rows]


async def test_real_refresh_updates_one_revision_preserves_old_and_idempotent_request(
    api, learning_app, web
):
    source, user, q, worker = await setup(api, learning_app, web)
    source_id = uuid.UUID(source["id"])
    before = await document_state(q, source_id)
    web.add(
        f"{DOCS}/guide/quickstart.html", page("Changed", "Yangi dalil 🙂 O‘zbekiston kitoblari.")
    )
    key = uuid.uuid4()
    first = await q.enqueue(user, source_id, key)
    assert (await q.enqueue(user, source_id, key))["id"] == first["id"]
    assert await worker.process_one()
    async with q.transaction(write=False) as session:
        run = await session.get(SourceRefreshRun, uuid.UUID(first["id"]))
        assert run.state == "completed" and run.attempts == 1
        assert run.result["changed"] == 1 and run.result["complete_fetch"]
        assert len(run.result["documents"]) <= 200
        for _, _, old_revision, _ in before:
            assert await session.get(DocumentRevision, old_revision) is not None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SourceRefreshBlob)
                .where(SourceRefreshBlob.published.is_(True))
            )
            == 1
        )
    replay = await q.enqueue(user, source_id, key)
    assert replay["id"] == first["id"] and replay["state"] == "completed"
    assert await q.claim() is None
    versions = (await api.get(f"/api/learning/sources/{source_id}/versions")).json()
    assert len(versions) == 2
    assert versions[0]["schema"] == "source-version-v2"
    assert versions[0]["previous_content_hash"] == versions[1]["content_hash"]


@pytest.mark.parametrize("control", ["cancel", "revoke"])
async def test_staged_work_cannot_publish_after_owner_control_and_old_data_survives(
    api, learning_app, web, control
):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    before = await document_state(q, sid)
    web.add(f"{DOCS}/guide/", page("Changed root", "Unpublished material must stay unpublished."))
    run = await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, prepared = await staged(q, worker)
    assert prepared
    # Actual separate transaction while no parsing/provider transaction is held.
    if control == "cancel":
        result = await q.cancel(user, sid, uuid.UUID(run["id"]))
        assert result["state"] == "cancelled"
    else:
        result = await q.configure(user, sid, enabled=False, interval_seconds=None)
        assert result["enabled"] is False
    with pytest.raises(JobError, match="authority"):
        await worker.publish(lease, inspection, prepared, budget)
    assert await document_state(q, sid) == before
    async with q.transaction(write=False) as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "learning.source_version")
            )
            == 1
        )
    with pytest.raises(JobError):
        await q.fail(lease, "internal_error")


async def test_expired_attempt_reclaimed_with_new_token_stale_worker_fenced(api, learning_app, web):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    run = await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, prepared = await staged(q, worker)
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshRun)
            .where(SourceRefreshRun.id == lease.run_id)
            .values(lease_until=await q.now(session) - timedelta(seconds=1))
        )
    replacement = await RefreshQueue(q.db).claim()  # independent worker instance
    assert replacement.run_id == lease.run_id and replacement.token != lease.token
    assert replacement.attempt == 2
    with pytest.raises(JobError):
        await worker.publish(lease, inspection, prepared, budget)
    await q.cancel(user, sid, uuid.UUID(run["id"]))
    assert await q.claim() is None


async def test_attempt_exhaustion_preserves_terminal_history_and_explicit_new_request(
    api, learning_app, web
):
    source, user, q, _ = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    key = uuid.uuid4()
    run = await q.enqueue(user, sid, key)
    for attempt in range(1, 4):
        lease = await q.claim()
        assert lease.attempt == attempt
        async with q.transaction() as session:
            await session.execute(
                update(SourceRefreshRun)
                .where(SourceRefreshRun.id == lease.run_id)
                .values(lease_until=await q.now(session) - timedelta(seconds=1))
            )
    assert await q.claim() is None
    exhausted = await q.enqueue(user, sid, key)
    assert exhausted["state"] == "failed" and exhausted["error_code"] == "attempts_exhausted"
    assert exhausted["attempts"] == 3
    new = await q.enqueue(user, sid, uuid.uuid4())
    assert new["id"] != run["id"] and new["attempts"] == 0


async def test_scheduler_requires_consent_coalesces_downtime_and_deduplicates(
    api, learning_app, web
):
    source, user, q, _ = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    assert await q.schedule_due() == 0
    await q.configure(user, sid, enabled=True, interval_seconds=3600)
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshPolicy)
            .where(SourceRefreshPolicy.source_id == sid)
            .values(next_run_at=await q.now(session) - timedelta(days=50))
        )
    assert await q.schedule_due() == 1
    assert await RefreshQueue(q.db).schedule_due() == 0
    async with q.transaction(write=False) as session:
        assert await session.scalar(select(func.count()).select_from(SourceRefreshRun)) == 1
        policy = await session.scalar(select(SourceRefreshPolicy))
        assert policy.next_run_at > await q.now(session)
    await q.configure(user, sid, enabled=False, interval_seconds=None)
    assert await q.claim() is None
    assert await q.schedule_due() == 0


async def test_revocation_blocks_next_network_request_and_redirect(api, learning_app, web):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    await q.enqueue(user, sid, uuid.uuid4())
    lease = await q.claim()
    await q.configure(user, sid, enabled=False, interval_seconds=None)
    before = list(web.requests)
    with pytest.raises(JobError):
        await worker.inspect(lease, Budget(Limits()))
    assert web.requests == before


async def test_partial_preserves_unseen_and_complete_withdrawal_preserves_history(
    api, learning_app, web
):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    old = await document_state(q, sid)
    await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, _prepared = await staged(q, worker)
    inspection.documents = inspection.documents[:1]
    inspection.stopped = "page_limit"
    await worker.publish(lease, inspection, [], budget)
    assert await document_state(q, sid) == old
    await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, _prepared = await staged(q, worker)
    inspection.documents = inspection.documents[:1]
    inspection.errors, inspection.stopped = [], None
    await worker.publish(lease, inspection, [], budget)
    after = await document_state(q, sid)
    assert sum(status == "removed" for _, _, _, status in after) == len(old) - 1
    async with q.transaction(write=False) as session:
        for _, _, revision, _ in old:
            assert await session.get(DocumentRevision, revision) is not None


async def test_atomic_publication_rolls_back_first_document_if_second_vector_write_fails(
    api, learning_app, web, monkeypatch
):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    old = await document_state(q, sid)
    web.add(
        f"{DOCS}/guide/",
        page("Root changed", "First changed source evidence.", ["quickstart.html"]),
    )
    web.add(
        f"{DOCS}/guide/quickstart.html", page("Child changed", "Second changed source evidence.")
    )
    await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, prepared = await staged(q, worker)
    assert len(prepared) == 2
    async with q.transaction(write=False) as session:
        store = await worker.learning.knowledge.vectors.get(session)
    real = store.upsert
    calls = 0

    async def fail_second(session, records):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled vector database failure")
        await real(session, records)

    monkeypatch.setattr(store, "upsert", fail_second)
    with pytest.raises(RuntimeError):
        await worker.publish(lease, inspection, prepared, budget)
    assert await document_state(q, sid) == old
    async with q.transaction(write=False) as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SourceRefreshBlob)
                .where(SourceRefreshBlob.published.is_(True))
            )
            == 0
        )


async def test_failed_staged_blob_cleanup_and_repeated_late_writer_cleanup(api, learning_app, web):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    web.add(f"{DOCS}/guide/", page("Changed root", "Staged raw source bytes."))
    await q.enqueue(user, sid, uuid.uuid4())
    lease, _budget, _inspection, prepared = await staged(q, worker)
    key = prepared[0].storage_key
    await q.cancel(user, sid, lease.run_id)
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshBlob).values(
                next_cleanup_at=await q.now(session) - timedelta(seconds=1)
            )
        )
    assert await worker.cleanup() == 1
    from ezo_api.storage.base import StorageError

    with pytest.raises(StorageError):
        await worker.learning.knowledge.storage.get(key)
    # A stale writer delayed after admission cannot publish; its late blob is
    # still cleaned because the cleanup tombstone was retained, not deleted.
    await worker.learning.knowledge.storage.put(key, b"late abandoned write")
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshBlob).values(
                next_cleanup_at=await q.now(session) - timedelta(seconds=1)
            )
        )
    assert await worker.cleanup() == 1
    with pytest.raises(StorageError):
        await worker.learning.knowledge.storage.get(key)


async def test_api_permissions_bounds_and_terminal_cancel_truth(api, learning_app, web):
    source, _user, _q, _ = await setup(api, learning_app, web)
    sid = source["id"]
    p = f"/api/learning/sources/{sid}"
    assert (await api.get(p + "/refresh-permission")).json()["recurring_consent"] is False
    assert (
        await api.put(p + "/refresh-permission", json={"enabled": True, "interval_seconds": 3600})
    ).status_code == 409
    assert (
        await api.put(
            p + "/refresh-permission",
            json={"enabled": True, "confirm": True, "interval_seconds": 1},
        )
    ).status_code == 422
    response = await api.post(p + "/refresh-runs", json={"request_id": str(uuid.uuid4())})
    assert response.status_code == 202, response.text
    result = response.json()
    assert result["state"] == "completed"
    assert (await api.post(p + f"/refresh-runs/{result['id']}/cancel")).json()[
        "state"
    ] == "completed"
    assert (await api.get(p + "/refresh-runs?limit=21")).status_code == 422
    assert (await api.get(p + "/refresh-runs?offset=100")).json() == []
    assert (
        await api.put(p + "/refresh-permission", json={"enabled": False, "confirm": True})
    ).status_code == 200
    assert (
        await api.post(p + "/refresh-runs", json={"request_id": str(uuid.uuid4())})
    ).status_code == 409
    unknown = f"/api/learning/sources/{uuid.uuid4()}"
    assert (await api.get(unknown + "/refresh-runs")).status_code == 404
    assert (
        await api.put(unknown + "/refresh-permission", json={"enabled": False})
    ).status_code == 404
    assert (await api.post(unknown + f"/refresh-runs/{result['id']}/cancel")).status_code == 404


@pytest.mark.parametrize("locked_table", [LearnedSource, SourceRefreshRun])
async def test_postgres_claim_skips_locked_source_and_run(api, learning_app, web, locked_table):
    if learning_app.state.services.db.engine.dialect.name != "postgresql":
        pytest.skip("Real PostgreSQL SKIP LOCKED required")
    source, user, q, _ = await setup(api, learning_app, web)
    other = await learn(api, f"{DOCS}/guide/", library_name="Independent source")
    first = await q.enqueue(user, uuid.UUID(source["id"]), uuid.uuid4())
    second = await q.enqueue(user, uuid.UUID(other["id"]), uuid.uuid4())
    async with q.db.sessionmaker() as lock:
        target = uuid.UUID(source["id"] if locked_table is LearnedSource else first["id"])
        await lock.scalar(select(locked_table).where(locked_table.id == target).with_for_update())
        claim = await asyncio.wait_for(RefreshQueue(q.db).claim(), 2)
        assert claim is not None and str(claim.run_id) == second["id"]
        await lock.rollback()
    claim = await asyncio.wait_for(RefreshQueue(q.db).claim(), 2)
    assert claim is not None and str(claim.run_id) == first["id"]


async def test_foreign_source_and_inconsistent_owner_cannot_block_valid_claim(
    api, learning_app, web
):
    from ezo_api.learning.service import get_library
    from tests.integration.test_document_jobs import seed

    source, user, q, _ = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    foreign = await seed(q.db)
    with pytest.raises(JobError) as denied:
        await q.enqueue(foreign.user, sid, uuid.uuid4())
    assert denied.value.status == 404
    first = await q.enqueue(user, sid, uuid.uuid4())
    second_source = await learn(api, f"{DOCS}/guide/", library_name="Healthy queue source")
    second = await q.enqueue(user, uuid.UUID(second_source["id"]), uuid.uuid4())
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshRun)
            .where(SourceRefreshRun.id == uuid.UUID(first["id"]))
            .values(created_at=await q.now(session) - timedelta(minutes=1))
        )
        other_library = await get_library(session, foreign.user, "Foreign")
        # All FKs are valid. Separate ownership links can be inconsistent after
        # an operator/import error; quarantine only that actual run.
        await session.execute(
            update(LearnedSource).where(LearnedSource.id == sid).values(library_id=other_library.id)
        )
    claim = await q.claim()
    assert claim is not None and str(claim.run_id) == second["id"]
    async with q.transaction(write=False) as session:
        poisoned = await session.get(SourceRefreshRun, uuid.UUID(first["id"]))
        assert poisoned.state == "failed" and poisoned.error_code == "scope_mismatch"


async def test_stored_stage_checksum_rejects_corruption_without_changing_publication(
    api, learning_app, web, monkeypatch
):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    before = await document_state(q, sid)
    web.add(f"{DOCS}/guide/", page("Changed", "Actual new source evidence."))
    run = await q.enqueue(user, sid, uuid.uuid4())
    real_put = worker.learning.knowledge.storage.put

    async def corrupt(key, data):
        await real_put(key, b"wrong stored bytes")

    monkeypatch.setattr(worker.learning.knowledge.storage, "put", corrupt)
    assert await worker.process_one()
    assert await document_state(q, sid) == before
    async with q.transaction(write=False) as session:
        row = await session.get(SourceRefreshRun, uuid.UUID(run["id"]))
        assert row.state == "failed" and row.error_code == "integrity_mismatch"
        assert await session.scalar(select(func.count()).select_from(SourceRefreshBlob)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(SourceRefreshBlob)
                .where(SourceRefreshBlob.published.is_(True))
            )
            == 0
        )


async def test_deadline_during_vector_publication_rolls_back_entire_result(
    api, learning_app, web, monkeypatch
):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    before = await document_state(q, sid)
    web.add(f"{DOCS}/guide/", page("Changed", "Actual changed source evidence."))
    await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, prepared = await staged(q, worker)
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshRun)
            .where(SourceRefreshRun.id == lease.run_id)
            .values(lease_until=await q.now(session) + timedelta(seconds=1))
        )
    async with q.transaction(write=False) as session:
        store = await worker.learning.knowledge.vectors.get(session)
    real = store.upsert

    async def delayed(session, records):
        await real(session, records)
        await asyncio.sleep(2.1)

    monkeypatch.setattr(store, "upsert", delayed)
    with pytest.raises(JobError) as expired:
        await worker.publish(lease, inspection, prepared, budget)
    assert expired.value.code == "stale_lease"
    assert await document_state(q, sid) == before


async def test_source_deletion_preserves_unpublished_cleanup_journal(api, learning_app, web):
    from ezo_api.storage.base import StorageError

    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    web.add(f"{DOCS}/guide/", page("Changed", "Unpublished source content."))
    await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, prepared = await staged(q, worker)
    key = prepared[0].storage_key
    await q.cancel(user, sid, lease.run_id)
    deleted = await api.delete(f"/api/learning/sources/{sid}")
    assert deleted.status_code == 204, deleted.text
    with pytest.raises(JobError):
        await worker.publish(lease, inspection, prepared, budget)
    async with q.transaction() as session:
        blob = await session.scalar(select(SourceRefreshBlob))
        assert blob.run_id is None and not blob.published
        blob.next_cleanup_at = await q.now(session) - timedelta(seconds=1)
    assert await worker.cleanup() == 1
    with pytest.raises(StorageError):
        await worker.learning.knowledge.storage.get(key)


async def test_only_due_expired_journal_is_cleaned_and_published_blob_survives(
    api, learning_app, web
):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    web.add(f"{DOCS}/guide/", page("Changed", "Published raw source content."))
    run = await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, prepared = await staged(q, worker)
    assert await worker.cleanup() == 0  # live writer, future GC deadline
    await worker.publish(lease, inspection, prepared, budget)
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshBlob).values(
                next_cleanup_at=await q.now(session) - timedelta(seconds=1)
            )
        )
    assert await worker.cleanup() == 0
    assert (
        await worker.learning.knowledge.storage.get(prepared[0].storage_key)
        == prepared[0].read.data
    )
    cancelled = await q.cancel(user, sid, uuid.UUID(run["id"]))
    assert cancelled["state"] == "completed"


async def test_revocation_after_redirect_response_blocks_next_hop(api, learning_app, web):
    import httpx

    from ezo_api.knowledge.fetch import SafeFetcher

    source, user, q, _worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    await q.enqueue(user, sid, uuid.uuid4())
    lease = await q.claim()
    requests = []

    async def handler(request):
        requests.append(str(request.url))
        await q.configure(user, sid, enabled=False, interval_seconds=None)
        return httpx.Response(302, headers={"location": "https://other.example.org/next"})

    async def resolve(host, port):
        return ["93.184.216.34"]

    fetcher = SafeFetcher(transport=httpx.MockTransport(handler), resolver=resolve).scoped(
        lambda: q.check(lease), lambda size: None
    )
    with pytest.raises(JobError):
        await fetcher.fetch(DOCS + "/redirect", respect_robots=False)
    assert requests == [DOCS + "/redirect"]


async def test_revocation_between_embedding_batches_blocks_next_provider_call(
    api, learning_app, web, fake_openai, monkeypatch
):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    await q.enqueue(user, sid, uuid.uuid4())
    lease = await q.claim()
    original = fake_openai.embed
    calls = 0

    async def embed(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = await original(*args, **kwargs)
        await q.configure(user, sid, enabled=False, interval_seconds=None)
        return result

    monkeypatch.setattr(fake_openai, "embed", embed)
    with pytest.raises(JobError):
        await worker.learning.knowledge.embeddings.embed_documents(
            ["Evidence"] * 65, before_batch=lambda: q.check(lease)
        )
    assert calls == 1


async def test_freshness_honesty_revocation_and_due_schedule(api, learning_app, web):
    source, user, q, _worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    endpoint = f"/api/learning/sources/{sid}/freshness"
    result = (await api.get(endpoint)).json()
    assert result["state"] == "verified_at_last_check"
    assert result["remote_change_known"] is False
    await q.configure(user, sid, enabled=True, interval_seconds=3600)
    async with q.transaction() as session:
        await session.execute(
            update(SourceRefreshPolicy)
            .where(SourceRefreshPolicy.source_id == sid)
            .values(next_run_at=await q.now(session) - timedelta(seconds=1))
        )
    assert (await api.get(endpoint)).json()["state"] == "check_due"
    await q.configure(user, sid, enabled=False, interval_seconds=None)
    assert (await api.get(endpoint)).json()["state"] == "permission_revoked"
    assert (await api.get(f"/api/learning/sources/{uuid.uuid4()}/freshness")).status_code == 404


async def test_revoked_permission_cannot_be_bypassed_by_legacy_runner(api, learning_app, web):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    await q.configure(user, sid, enabled=False, interval_seconds=None)
    before = list(web.requests)
    await worker.learning.run(sid)
    assert web.requests == before
    assert (await api.post(f"/api/learning/sources/{sid}/refresh")).status_code == 409


async def test_deleting_other_source_preserves_shared_historical_revision_blob(
    api, learning_app, web
):
    source, user, q, worker = await setup(api, learning_app, web)
    other = await learn(api, f"{DOCS}/guide/", library_name="Retained history")
    async with q.transaction(write=False) as session:
        row = await session.scalar(
            select(KnowledgeDocument)
            .join(LearnedSource, LearnedSource.knowledge_source_id == KnowledgeDocument.source_id)
            .where(
                LearnedSource.id == uuid.UUID(other["id"]),
                KnowledgeDocument.source_url == DOCS + "/guide/",
            )
        )
        old_revision = await session.get(DocumentRevision, row.current_revision_id)
        old_key = old_revision.storage_key
        old_bytes = await worker.learning.knowledge.storage.get(old_key)
    web.add(f"{DOCS}/guide/", page("New root", "Changed source evidence."))
    await q.enqueue(user, uuid.UUID(other["id"]), uuid.uuid4())
    assert await worker.process_one()
    deleted = await api.delete(f"/api/learning/sources/{source['id']}")
    assert deleted.status_code == 204, deleted.text
    assert await worker.learning.knowledge.storage.get(old_key) == old_bytes


async def test_production_like_website_initial_read_and_durable_refresh_use_no_native_parser(
    api, learning_app, web, monkeypatch
):
    from ezo_api.knowledge.ingestion import service as ingestion_service
    from ezo_api.knowledge.parsers import html
    from ezo_api.learning import refresh_worker

    monkeypatch.setattr(ingestion_service, "native_fixtures_allowed", lambda: False)
    monkeypatch.setattr(refresh_worker, "native_fixtures_allowed", lambda: False)
    monkeypatch.setattr(html, "native_fixtures_allowed", lambda: False)

    def no_native(*args, **kwargs):
        raise AssertionError("Native HTML must not run in the API")

    monkeypatch.setattr(html.trafilatura, "extract", no_native)
    source, user, q, worker = await setup(api, learning_app, web)
    assert source["status"] == "indexed"
    web.add(f"{DOCS}/guide/", page("New evidence", "O‘zbekiston 🙂 yangi dalil."))
    run = await q.enqueue(user, uuid.UUID(source["id"]), uuid.uuid4())
    assert await worker.process_one()
    async with q.transaction(write=False) as session:
        result = await session.get(SourceRefreshRun, uuid.UUID(run["id"]))
        assert result.state == "completed"
        document = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.current_revision_id.is_not(None),
                KnowledgeDocument.source_url == DOCS + "/guide/",
            )
        )
        revision = await session.get(DocumentRevision, document.current_revision_id)
        assert "O‘zbekiston 🙂 yangi dalil." in revision.raw_text


async def test_new_source_url_is_published_and_withdrawn_url_can_return(api, learning_app, web):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    old = await document_state(q, sid)
    # A completely new URL and a complete observation withdraw old children.
    web.add(f"{DOCS}/guide/", page("Root", "Root evidence.", ["new.html"]))
    web.add(f"{DOCS}/guide/new.html", page("New", "New URL evidence."))
    await q.enqueue(user, sid, uuid.uuid4())
    assert await worker.process_one()
    async with q.transaction(write=False) as session:
        result = await session.scalar(select(SourceRefreshRun))
        assert result.state == "completed"
        assert len(result.result["documents"]) == 2
    docs_site(web)  # The same historic URLs legitimately reappear at the source.
    await q.enqueue(user, sid, uuid.uuid4())
    assert await worker.process_one()
    after = await document_state(q, sid)
    assert sum(s == "indexed" for _, _, _, s in after) == len(old)
    async with q.transaction(write=False) as session:
        for _, _, rev, _ in old:
            assert await session.get(DocumentRevision, rev) is not None


async def test_partial_refresh_and_revoked_fetch_are_labelled_in_retrieval(api, learning_app, web):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    await q.enqueue(user, sid, uuid.uuid4())
    lease, budget, inspection, _prepared = await staged(q, worker)
    inspection.documents = inspection.documents[:1]
    inspection.stopped = "page_limit"
    await worker.publish(lease, inspection, [], budget)
    search = await api.post("/api/knowledge/search", json={"query": "widget.connect token session"})
    assert search.status_code == 200
    hits = search.json()["results"]
    assert any(hit["freshness_status"] == "not_recently_checked" for hit in hits)
    await q.configure(user, sid, enabled=False, interval_seconds=None)
    hits = (
        await api.post("/api/knowledge/search", json={"query": "widget.connect token session"})
    ).json()["results"]
    assert hits and all(hit["freshness_status"] == "permission_revoked" for hit in hits)


async def test_corrupt_input_identity_is_quarantined_before_fetch(api, learning_app, web):
    source, user, q, _worker = await setup(api, learning_app, web)
    first = await q.enqueue(user, uuid.UUID(source["id"]), uuid.uuid4())
    other = await learn(api, DOCS + "/guide/", library_name="Valid next job")
    second = await q.enqueue(user, uuid.UUID(other["id"]), uuid.uuid4())
    async with q.transaction() as session:
        run = await session.get(SourceRefreshRun, uuid.UUID(first["id"]))
        run.input = {**run.input, "target": "http://127.0.0.1/private"}
        run.created_at = await q.now(session) - timedelta(minutes=1)
    requests = list(web.requests)
    claim = await q.claim()
    assert claim is not None and str(claim.run_id) == second["id"]
    assert web.requests == requests
    async with q.transaction(write=False) as session:
        run = await session.get(SourceRefreshRun, uuid.UUID(first["id"]))
        assert run.state == "failed" and run.error_code == "input_mismatch"


async def test_global_learning_off_blocks_new_and_legacy_recovery_fetches(api, learning_app, web):
    source, user, q, worker = await setup(api, learning_app, web)
    sid = uuid.UUID(source["id"])
    await q.enqueue(user, sid, uuid.uuid4())
    worker.learning.enabled = False
    before = list(web.requests)
    assert await worker.process_one() is False
    await worker.learning.run(sid)
    assert await learning_app.state.services.learning.resume_unfinished() == 0
    assert web.requests == before


async def test_owner_history_quota_serializes_concurrent_different_source_admission(
    api, learning_app, web, monkeypatch
):
    from ezo_api.learning import refresh

    source, user, q, _worker = await setup(api, learning_app, web)
    other = await learn(api, DOCS + "/guide/", library_name="Concurrent quota")
    monkeypatch.setattr(refresh, "MAX_RUNS_PER_USER", 1)
    results = await asyncio.gather(
        q.enqueue(user, uuid.UUID(source["id"]), uuid.uuid4()),
        RefreshQueue(q.db).enqueue(user, uuid.UUID(other["id"]), uuid.uuid4()),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    rejected = [r for r in results if isinstance(r, JobError)]
    assert len(rejected) == 1 and rejected[0].code == "history_limit"
    async with q.transaction(write=False) as session:
        assert await session.scalar(select(func.count()).select_from(SourceRefreshRun)) == 1
