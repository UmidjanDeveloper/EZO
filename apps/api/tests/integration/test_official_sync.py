"""Official-source synchronization against a real database and a scripted (mocked) website.

No live LEX.UZ traffic happens here: these tests prove the framework's rules, not
that LEX.UZ itself works with EZO (see docs/OFFICIAL_SOURCES.md).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DocumentRevision,
    KnowledgeDocument,
    LegalDocument,
    LegalRevision,
    OfficialSyncRun,
)
from ezo_api.main import create_app
from ezo_api.official.base import SourceNotEnabledError, UnsupportedSourceError
from ezo_api.official.sync import OfficialSyncService, official_knowledge_ids
from ezo_api.services import Services
from tests.conftest import make_settings
from tests.official_fixtures import (
    LRU_682,
    RUSSIAN,
    UZ_CYRILLIC,
    UZ_LATIN,
    FakeSite,
    Sleeps,
    amended,
    html,
    with_status,
)


@dataclass
class Env:
    services: Services
    session: AsyncSession
    site: FakeSite
    sleeps: Sleeps
    sync: OfficialSyncService
    user_id: uuid.UUID


@pytest.fixture
async def env(database_url: str) -> AsyncIterator[Env]:
    settings = make_settings(
        database_url, EZO_OFFICIAL_SOURCES="lexuz", EZO_OFFICIAL_MIN_INTERVAL_SECONDS="2"
    )
    app: FastAPI = create_app(settings, providers={})
    services: Services = app.state.services
    site = FakeSite()
    sleeps = Sleeps()
    sync = OfficialSyncService(
        settings,
        services.knowledge,
        site.fetcher(),
        services.storage,
        sleep=sleeps,
        clock=sleeps.clock,
    )
    async with services.db.sessionmaker() as session:
        user = await services.auth.ensure_owner(session)
        await session.commit()
        yield Env(services, session, site, sleeps, sync, user.id)
    await services.db.dispose()


async def legal(env: Env, doc_id: str = LRU_682, language: str = "uz") -> LegalDocument:
    row = await env.session.scalar(
        select(LegalDocument).where(
            LegalDocument.source_doc_id == doc_id, LegalDocument.language == language
        )
    )
    assert row is not None
    return row


async def revisions(env: Env, row: LegalDocument) -> list[LegalRevision]:
    return list(
        (
            await env.session.scalars(
                select(LegalRevision)
                .where(LegalRevision.legal_document_id == row.id)
                .order_by(LegalRevision.revision_number)
            )
        ).all()
    )


async def test_new_document_is_stored_with_metadata_and_indexed(env: Env) -> None:
    env.site.routes[f"/docs/{LRU_682}"] = html(UZ_LATIN)
    run = await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "uz")
    assert run.status == "completed" and run.counts["new"] == 1
    assert env.site.log == ["/robots.txt", f"/docs/{LRU_682}"]
    assert run.requests_made == 2

    row = await legal(env)
    assert row.document_number == "O‘RQ-682" and row.document_type == "law"
    assert row.authority == "Oliy Majlis" and str(row.adopted_on) == "2021-04-20"
    assert row.title == "Normativ-huquqiy hujjatlar toʻgʻrisida"
    assert row.official_url == f"https://lex.uz/docs/{LRU_682}"
    assert row.script == "latn" and row.last_retrieved_at is not None
    assert row.status == "unknown" and row.status_verified_at is None  # never assumed
    assert row.provenance["connector"] == "lexuz" and row.provenance["access"] == "public_web_pages"

    [revision] = await revisions(env, row)
    assert revision.revision_number == 1 and revision.raw_storage_key
    raw = await env.services.storage.get(revision.raw_storage_key)
    assert raw == UZ_LATIN.encode()  # the page exactly as received

    document = await env.session.get(KnowledgeDocument, row.knowledge_document_id)
    assert document is not None and document.status in ("indexed", "partial")
    assert document.source_url == row.official_url and document.chunk_count >= 1
    indexed = await env.session.get(DocumentRevision, document.current_revision_id)
    assert indexed is not None
    assert "## 1-modda." in indexed.raw_text and "## 2-modda." in indexed.raw_text
    assert revision.knowledge_revision_id == document.current_revision_id


async def test_resync_detects_unchanged_and_amended_without_losing_history(env: Env) -> None:
    path = f"/docs/{LRU_682}"
    env.site.routes[path] = html(UZ_LATIN)
    await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "uz")
    again = await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "uz")
    assert again.counts["unchanged"] == 1
    row = await legal(env)
    assert len(await revisions(env, row)) == 1

    env.site.routes[path] = html(amended(UZ_LATIN))
    third = await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "uz")
    assert third.counts["amended"] == 1
    await env.session.refresh(row)
    history = await revisions(env, row)
    assert [r.revision_number for r in history] == [1, 2]
    assert history[0].content_hash != history[1].content_hash
    assert row.current_revision_id == history[1].id
    knowledge_revisions = await env.session.scalar(
        select(func.count())
        .select_from(DocumentRevision)
        .where(DocumentRevision.document_id == row.knowledge_document_id)
    )
    assert knowledge_revisions == 2  # the old text is kept, only the new one is searchable
    old = await env.session.get(DocumentRevision, history[0].knowledge_revision_id)
    assert old is not None and "3-modda" not in old.raw_text


async def test_same_text_under_another_id_is_a_duplicate(env: Env) -> None:
    env.site.routes[f"/docs/{LRU_682}"] = html(UZ_LATIN)
    env.site.routes["/docs/777"] = html(UZ_LATIN)
    run = await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682, "777", LRU_682], "uz")
    assert run.requested == [LRU_682, "777"]  # repeated IDs are synced once
    assert run.counts["new"] == 1 and run.counts["duplicate"] == 1
    copy = await legal(env, "777")
    original = await legal(env)
    assert copy.duplicate_of_id == original.id and copy.knowledge_document_id is None
    documents = await env.session.scalar(select(func.count()).select_from(KnowledgeDocument))
    assert documents == 1


async def test_outdated_documents_are_filtered_from_current_law(env: Env) -> None:
    env.site.routes[f"/docs/{LRU_682}"] = html(with_status(UZ_LATIN, "Kuchini yoʻqotgan"))
    env.site.routes["/docs/2"] = html(with_status(amended(UZ_LATIN), "Amaldagi"))
    await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682, "2"], "uz")
    repealed, current = await legal(env), await legal(env, "2")
    assert repealed.status == "repealed" and repealed.status_source == "source_text"
    assert repealed.status_verified_at is not None
    assert current.status == "in_force"
    now_ids = await official_knowledge_ids(env.session, env.user_id, include_outdated=False)
    all_ids = await official_knowledge_ids(env.session, env.user_id, include_outdated=True)
    assert now_ids == {current.knowledge_document_id}
    assert all_ids == {current.knowledge_document_id, repealed.knowledge_document_id}


async def test_cyrillic_and_russian_texts(env: Env) -> None:
    env.site.routes[f"/docs/{LRU_682}"] = html(UZ_CYRILLIC)
    env.site.routes[f"/ru/docs/{LRU_682}"] = html(RUSSIAN)
    await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "uz")
    await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "ru")
    uz, ru = await legal(env, language="uz"), await legal(env, language="ru")
    assert (uz.script, uz.document_number) == ("cyrl", "ЎРҚ-682")
    assert (ru.script, ru.document_number, ru.title) == (
        "cyrl",
        "ЗРУ-682",
        "О нормативно-правовых актах",
    )
    assert ru.official_url == f"https://lex.uz/ru/docs/{LRU_682}"


async def test_interrupted_run_is_recovered_and_resumed(env: Env) -> None:
    for doc_id, page in (("11", UZ_LATIN), ("12", amended(UZ_LATIN)), ("13", UZ_CYRILLIC)):
        env.site.routes[f"/docs/{doc_id}"] = html(page)
    # A run that died after the first document (no heartbeat for an hour).
    dead = OfficialSyncRun(
        user_id=env.user_id,
        connector="lexuz",
        language="uz",
        requested=["11", "12", "13"],
        done=["11"],
        counts={"new": 1},
        heartbeat_at=utcnow() - timedelta(hours=1),
    )
    env.session.add(dead)
    await env.session.commit()
    assert await env.sync.recover_interrupted(env.session) == 1
    assert dead.status == "interrupted"
    resumed = await env.sync.resume(env.session, env.user_id, dead.id)
    assert resumed.requested == ["12", "13"] and resumed.resumed_from_id == dead.id
    assert resumed.status == "completed" and resumed.counts["new"] == 2
    assert "/docs/11" not in env.site.log  # finished work is not repeated
    with pytest.raises(UnsupportedSourceError, match="cannot be resumed"):
        await env.sync.resume(env.session, env.user_id, resumed.id)


async def test_network_failures_are_recorded_and_stop_after_repeats(env: Env) -> None:
    def down() -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    for doc_id in ("21", "22", "23", "24"):
        env.site.routes[f"/docs/{doc_id}"] = down
    run = await env.sync.start(env.session, env.user_id, "lexuz", ["21", "22", "23", "24"], "uz")
    assert run.status == "partial" and run.counts["failed"] == 3
    assert "repeated failures" in (run.error or "")
    assert "/docs/24" not in env.site.log
    assert await env.session.scalar(select(func.count()).select_from(LegalDocument)) == 0


async def test_access_refusal_blocks_the_run_without_retrying(env: Env) -> None:
    env.site.routes["/docs/31"] = httpx.Response(403)
    env.site.routes["/docs/32"] = html(UZ_LATIN)
    run = await env.sync.start(env.session, env.user_id, "lexuz", ["31", "32"], "uz")
    assert run.status == "blocked" and "does not work around" in (run.error or "")
    assert env.site.log.count("/docs/31") == 1 and "/docs/32" not in env.site.log


async def test_robots_disallow_blocks_and_rate_limits_are_honoured(env: Env) -> None:
    env.site.robots = httpx.Response(200, text="User-agent: *\nDisallow: /docs/\n")
    env.site.routes["/docs/41"] = html(UZ_LATIN)
    blocked = await env.sync.start(env.session, env.user_id, "lexuz", ["41"], "uz")
    assert blocked.status == "blocked" and "/docs/41" not in env.site.log

    env.site.robots = httpx.Response(404)
    env.sync.fetcher = env.site.fetcher()  # fresh robots cache
    answers = [httpx.Response(429, headers={"retry-after": "3"}), html(UZ_LATIN)]
    env.site.routes["/docs/42"] = lambda: answers.pop(0)
    ok = await env.sync.start(env.session, env.user_id, "lexuz", ["42"], "uz")
    assert ok.status == "completed" and 3.0 in env.sleeps.calls

    env.site.routes["/docs/43"] = httpx.Response(429, headers={"retry-after": "999"})
    slow = await env.sync.start(env.session, env.user_id, "lexuz", ["43"], "uz")
    assert slow.status == "partial" and "slow down" in (slow.error or "")
    assert 999.0 not in env.sleeps.calls  # never waits longer than allowed


async def test_requests_are_spaced_by_the_minimum_interval(env: Env) -> None:
    for doc_id in ("51", "52", "53"):
        env.site.routes[f"/docs/{doc_id}"] = html(
            amended(UZ_LATIN).replace("3-modda", f"{doc_id}-modda")
        )
    await env.sync.start(env.session, env.user_id, "lexuz", ["51", "52", "53"], "uz")
    # robots + 3 documents → 3 waits; each at least the connector floor (5 s > setting 2 s)
    assert len(env.sleeps.calls) == 3 and all(wait >= 4.9 for wait in env.sleeps.calls)


async def test_unsupported_and_disabled_sources(env: Env, database_url: str) -> None:
    for key in ("govuz", "presidentuz", "eqaror"):
        with pytest.raises(UnsupportedSourceError):
            await env.sync.start(env.session, env.user_id, key, ["1"], "uz")
    with pytest.raises(UnsupportedSourceError, match="digits only"):
        await env.sync.start(env.session, env.user_id, "lexuz", ["../admin"], "uz")
    with pytest.raises(UnsupportedSourceError, match="not en"):
        await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "en")
    off = OfficialSyncService(
        make_settings(database_url),
        env.services.knowledge,
        env.site.fetcher(),
        env.services.storage,
    )
    with pytest.raises(SourceNotEnabledError):
        await off.start(env.session, env.user_id, "lexuz", [LRU_682], "uz")
    assert env.site.log == []  # nothing was ever requested


async def test_live_verification_and_honest_failure(env: Env) -> None:
    path = f"/docs/{LRU_682}"
    env.site.routes[path] = html(UZ_LATIN)
    await env.sync.start(env.session, env.user_id, "lexuz", [LRU_682], "uz")
    row = await legal(env)
    first_retrieval = row.last_retrieved_at

    env.sync.fetcher = env.site.fetcher()
    check = await env.sync.verify_live(env.session, row)
    assert check.state == "verified" and check.checked_at is not None

    env.site.routes[path] = html(amended(UZ_LATIN))
    env.sync.fetcher = env.site.fetcher()
    changed = await env.sync.verify_live(env.session, row)
    assert changed.state == "changed" and len(await revisions(env, row)) == 2

    def down() -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    env.site.routes[path] = down
    env.sync.fetcher = env.site.fetcher()
    await env.session.refresh(row)
    verified_at = row.last_retrieved_at
    failed = await env.sync.verify_live(env.session, row)
    assert failed.state == "failed" and failed.last_verified_at == verified_at
    assert verified_at is not None and first_retrieval is not None
    assert row.last_check_error and row.last_retrieved_at == verified_at
