"""Incremental, rate-limited synchronization of official documents.

A run re-checks the documents the user tracks (by their source IDs):

    fetch (OfficialHttpClient) → parse (connector) → compare content hash
      unchanged → only "last retrieved" moves
      new       → knowledge document + revision 1
      changed   → new knowledge revision + new LegalRevision (history kept)
      same text under another ID → recorded as a duplicate, not indexed twice

Progress is committed after every document (`OfficialSyncRun.done`), so a run that
dies (API restart, crash) is marked `interrupted` and can be resumed where it
stopped. Access refusals stop the run (`blocked`) and are never retried; rate
limits are honoured (Retry-After up to a cap, otherwise the run stops `partial`).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import KnowledgeDocument, LegalDocument, LegalRevision, OfficialSyncRun
from ezo_api.knowledge.fetch import FetchedPage, SafeFetcher
from ezo_api.knowledge.ingestion.service import KnowledgeService
from ezo_api.official.base import (
    AccessRestrictedError,
    BudgetExhaustedError,
    DocumentParseError,
    DocumentRef,
    OfficialSourceConnector,
    OfficialSourceError,
    ParsedLegalDocument,
    RateLimitedError,
    RobotsUnavailableError,
    TemporaryFetchError,
    UnsupportedSourceError,
)
from ezo_api.official.http import OfficialHttpClient, Sleep
from ezo_api.official.registry import get_connector
from ezo_api.settings import Settings
from ezo_api.storage.base import StorageProvider

logger = logging.getLogger(__name__)

Outcome = Literal["new", "amended", "unchanged", "duplicate"]
MAX_CONSECUTIVE_FAILURES = 3
STALE_RUN = timedelta(minutes=15)
COUNT_KEYS = ("new", "amended", "unchanged", "duplicate", "failed", "skipped")


def text_hash(text: str) -> str:
    normalized = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LiveCheck:
    state: Literal["verified", "changed", "failed", "disabled"]
    checked_at: datetime | None
    last_verified_at: datetime | None
    message: str = ""


class OfficialSyncService:
    def __init__(
        self,
        settings: Settings,
        knowledge: KnowledgeService,
        fetcher: SafeFetcher,
        storage: StorageProvider,
        sleep: Sleep | None = None,
    ) -> None:
        self.settings = settings
        self.knowledge = knowledge
        self.fetcher = fetcher
        self.storage = storage
        self._sleep = sleep

    @property
    def enabled(self) -> list[str]:
        return list(self.settings.official_sources)

    def connector(self, key: str) -> OfficialSourceConnector:
        return get_connector(key, self.enabled)

    def client(self, connector: OfficialSourceConnector, max_requests: int) -> OfficialHttpClient:
        return OfficialHttpClient(
            self.fetcher,
            connector.policy,
            min_interval=self.settings.official_min_interval_seconds,
            max_requests=max_requests,
            sleep=self._sleep,
        )

    # ------------------------------------------------------------------ runs

    async def recover_interrupted(
        self, session: AsyncSession, stale_after: timedelta = STALE_RUN
    ) -> int:
        """Mark runs whose process died (no heartbeat) as interrupted. Returns how many."""
        cutoff = utcnow() - stale_after
        runs = (
            await session.scalars(
                select(OfficialSyncRun).where(
                    OfficialSyncRun.status == "running", OfficialSyncRun.heartbeat_at < cutoff
                )
            )
        ).all()
        for run in runs:
            run.status = "interrupted"
            run.error = "The run stopped unexpectedly (e.g. an API restart). It can be resumed."
            run.finished_at = utcnow()
        await session.commit()
        return len(runs)

    async def start(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        key: str,
        source_doc_ids: list[str],
        language: str,
    ) -> OfficialSyncRun:
        connector = self.connector(key)
        if language not in connector.policy.languages:
            raise UnsupportedSourceError(
                f"{connector.policy.name} documents are available in "
                f"{', '.join(connector.policy.languages)}, not {language}."
            )
        ids: list[str] = []
        for raw in source_doc_ids:
            value = connector.validate_id(raw)
            if value not in ids:
                ids.append(value)
        if not ids:
            raise UnsupportedSourceError("Name at least one document ID to synchronize.")
        if len(ids) > self.settings.official_max_documents_per_run:
            raise UnsupportedSourceError(
                f"At most {self.settings.official_max_documents_per_run} documents per run "
                "(EZO_OFFICIAL_MAX_DOCUMENTS_PER_RUN)."
            )
        run = OfficialSyncRun(
            user_id=user_id,
            connector=key,
            language=language,
            requested=ids,
            done=[],
            counts=dict.fromkeys(COUNT_KEYS, 0),
        )
        session.add(run)
        await session.commit()
        await self._execute(session, run, connector)
        return run

    async def resume(
        self, session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID
    ) -> OfficialSyncRun:
        previous = await session.get(OfficialSyncRun, run_id)
        if previous is None or previous.user_id != user_id:
            raise UnsupportedSourceError("This synchronization run does not exist.")
        if previous.status not in ("interrupted", "partial", "failed"):
            raise UnsupportedSourceError(f"A {previous.status} run cannot be resumed.")
        connector = self.connector(previous.connector)
        remaining = [i for i in previous.requested if i not in previous.done]
        run = OfficialSyncRun(
            user_id=user_id,
            connector=previous.connector,
            language=previous.language,
            requested=remaining,
            done=[],
            counts=dict.fromkeys(COUNT_KEYS, 0),
            resumed_from_id=previous.id,
        )
        session.add(run)
        await session.commit()
        await self._execute(session, run, connector)
        return run

    def _count(self, run: OfficialSyncRun, key: str) -> None:
        run.counts = {**run.counts, key: int(run.counts.get(key, 0)) + 1}

    async def _execute(
        self, session: AsyncSession, run: OfficialSyncRun, connector: OfficialSourceConnector
    ) -> None:
        # robots.txt + one request per document, plus room for one Retry-After retry.
        client = self.client(connector, max_requests=2 * len(run.requested) + 2)
        failures = 0
        status = "completed"
        errors: list[str] = []
        for doc_id in list(run.requested):
            ref = DocumentRef(doc_id, run.language)
            try:
                outcome = await self._sync_one(session, run.user_id, connector, client, ref)
            except AccessRestrictedError as exc:
                status, errors = "blocked", [exc.message]
                break
            except RobotsUnavailableError as exc:
                status, errors = "partial", [exc.message]
                break
            except BudgetExhaustedError as exc:
                status, errors = "partial", [exc.message]
                break
            except RateLimitedError as exc:
                status, errors = "partial", [exc.message]
                break
            except (TemporaryFetchError, DocumentParseError, UnsupportedSourceError) as exc:
                failures += 1
                self._count(run, "failed")
                errors.append(f"{doc_id}: {exc.message}")
                run.done = [*run.done, doc_id]
                run.heartbeat_at = utcnow()
                run.requests_made = client.requests_made
                await session.commit()
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    status = "partial"
                    errors.append("Stopped after repeated failures.")
                    break
                continue
            failures = 0
            self._count(run, outcome)
            run.done = [*run.done, doc_id]
            run.heartbeat_at = utcnow()
            run.requests_made = client.requests_made
            await session.commit()
        if status == "completed" and run.counts.get("failed"):
            status = "partial"
        run.status = status
        run.error = "\n".join(errors)[:4000] or None
        run.requests_made = client.requests_made
        run.finished_at = utcnow()
        await session.commit()

    async def _sync_one(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        connector: OfficialSourceConnector,
        client: OfficialHttpClient,
        ref: DocumentRef,
    ) -> Outcome:
        page = await self._fetch(client, connector.document_url(ref))
        parsed = connector.parse(page, ref)
        return await self.store(session, user_id, connector, parsed, page)

    async def _fetch(self, client: OfficialHttpClient, url: str) -> FetchedPage:
        try:
            return await client.get(url)
        except RateLimitedError as exc:
            wait = exc.retry_after
            if wait is None or wait > self.settings.official_max_retry_after_seconds:
                raise
            sleep = self._sleep or client._sleep
            await sleep(wait)
            return await client.get(url)  # once; a second 429 stops the run

    # ------------------------------------------------------------------ storing

    async def store(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        connector: OfficialSourceConnector,
        parsed: ParsedLegalDocument,
        page: FetchedPage,
    ) -> Outcome:
        now = utcnow()
        key = connector.policy.key
        content_hash = text_hash(parsed.text)
        legal = await session.scalar(
            select(LegalDocument).where(
                LegalDocument.user_id == user_id,
                LegalDocument.connector == key,
                LegalDocument.source_doc_id == parsed.source_doc_id,
                LegalDocument.language == parsed.language,
            )
        )
        if legal is not None and legal.content_hash == content_hash:
            legal.last_retrieved_at = legal.last_checked_at = now
            legal.last_check_error = None
            self._apply_status(legal, parsed, now)
            return "unchanged"

        raw_digest = hashlib.sha256(page.data).hexdigest()
        raw_key = f"official/{user_id}/{key}/raw/{raw_digest[:2]}/{raw_digest}.html"
        if not await self.storage.exists(raw_key):
            await self.storage.put(raw_key, page.data)

        original = await session.scalar(
            select(LegalDocument).where(
                LegalDocument.user_id == user_id,
                LegalDocument.content_hash == content_hash,
                LegalDocument.duplicate_of_id.is_(None),
                LegalDocument.source_doc_id != parsed.source_doc_id,
            )
        )
        outcome: Outcome = "amended" if legal is not None else "new"
        knowledge_revision_id: uuid.UUID | None = None
        knowledge_document_id: uuid.UUID | None = None
        if original is not None:
            outcome = "duplicate"
        else:
            added = await self.knowledge.add_connector_document(
                session,
                user_id,
                source_name=connector.policy.name,
                source_url=parsed.official_url,
                filename=f"{key}-{parsed.source_doc_id}-{parsed.language}.md",
                title=parsed.title,
                markdown=parsed.text,
                meta={
                    "official": True,
                    "connector": key,
                    "source_doc_id": parsed.source_doc_id,
                    "document_number": parsed.document_number,
                },
            )
            document = await self.knowledge.ingest(session, added.document.id)
            knowledge_revision_id = document.current_revision_id
            knowledge_document_id = document.id

        if legal is None:
            legal = LegalDocument(
                user_id=user_id,
                connector=key,
                source_doc_id=parsed.source_doc_id,
                language=parsed.language,
                title=parsed.title,
                official_url=parsed.official_url,
                content_hash=content_hash,
                provenance={},
            )
            session.add(legal)
        legal.script = parsed.script
        legal.title = parsed.title
        legal.document_number = parsed.document_number
        legal.document_type = parsed.document_type
        legal.authority = parsed.authority
        legal.adopted_on = parsed.adopted_on
        legal.published_on = parsed.published_on
        legal.effective_on = parsed.effective_on
        legal.official_url = parsed.official_url
        legal.content_hash = content_hash
        legal.last_retrieved_at = legal.last_checked_at = now
        legal.last_check_error = None
        legal.duplicate_of_id = original.id if original is not None else None
        if original is None:
            legal.knowledge_document_id = knowledge_document_id
        legal.provenance = {
            "connector": key,
            "access": connector.policy.access,
            "fetched_url": page.url,
            "final_url": page.final_url,
            "content_type": page.content_type,
            "fetched_at": page.fetched_at,
            "warnings": parsed.warnings,
        }
        self._apply_status(legal, parsed, now)
        await session.flush()
        number = (
            await session.scalar(
                select(func.max(LegalRevision.revision_number)).where(
                    LegalRevision.legal_document_id == legal.id
                )
            )
            or 0
        ) + 1
        revision = LegalRevision(
            legal_document_id=legal.id,
            revision_number=number,
            revision_label=parsed.revision_label,
            content_hash=content_hash,
            knowledge_revision_id=knowledge_revision_id,
            title=parsed.title,
            status=parsed.status,
            official_url=parsed.official_url,
            raw_storage_key=raw_key,
            retrieved_at=now,
            meta={"warnings": parsed.warnings},
        )
        session.add(revision)
        await session.flush()
        legal.current_revision_id = revision.id
        await session.flush()
        return outcome

    @staticmethod
    def _apply_status(legal: LegalDocument, parsed: ParsedLegalDocument, now: datetime) -> None:
        legal.status = parsed.status
        legal.status_source = parsed.status_source
        legal.status_verified_at = now if parsed.status_source == "source_text" else None

    # ------------------------------------------------------------------ live check

    async def verify_live(self, session: AsyncSession, legal: LegalDocument) -> LiveCheck:
        """Re-fetch the official document now. A changed text is stored as a new revision."""
        last = legal.last_retrieved_at
        try:
            connector = self.connector(legal.connector)
        except OfficialSourceError as exc:
            return LiveCheck("disabled", None, last, exc.message)
        client = self.client(connector, max_requests=3)
        ref = DocumentRef(legal.source_doc_id, legal.language)
        now = utcnow()
        try:
            page = await client.get(connector.document_url(ref))
            parsed = connector.parse(page, ref)
            outcome = await self.store(session, legal.user_id, connector, parsed, page)
        except OfficialSourceError as exc:
            legal.last_checked_at = now
            legal.last_check_error = exc.message[:1000]
            await session.commit()
            return LiveCheck("failed", now, last, exc.message)
        await session.commit()
        return LiveCheck(
            "verified" if outcome == "unchanged" else "changed",
            now,
            legal.last_retrieved_at,
            ""
            if outcome == "unchanged"
            else "The official text has changed; a new revision was saved.",
        )


async def legal_documents_for(
    session: AsyncSession, user_id: uuid.UUID, knowledge_ids: list[uuid.UUID]
) -> dict[uuid.UUID, LegalDocument]:
    if not knowledge_ids:
        return {}
    rows = (
        await session.scalars(
            select(LegalDocument).where(
                LegalDocument.user_id == user_id,
                LegalDocument.knowledge_document_id.in_(knowledge_ids),
            )
        )
    ).all()
    return {row.knowledge_document_id: row for row in rows if row.knowledge_document_id}


async def official_knowledge_ids(
    session: AsyncSession, user_id: uuid.UUID, *, include_outdated: bool
) -> frozenset[uuid.UUID]:
    """Knowledge documents that hold official texts; outdated ones only when asked for."""
    statement = select(LegalDocument.knowledge_document_id).where(
        LegalDocument.user_id == user_id,
        LegalDocument.knowledge_document_id.is_not(None),
        LegalDocument.duplicate_of_id.is_(None),
    )
    if not include_outdated:
        statement = statement.where(LegalDocument.status.not_in(("repealed", "expired")))
    ids = (await session.scalars(statement)).all()
    present = (
        await session.scalars(select(KnowledgeDocument.id).where(KnowledgeDocument.id.in_(ids)))
    ).all()
    return frozenset(present)
