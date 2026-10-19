"""Unit tests for Phase K2: Library-Scoped Retrieval & Chat Integration.

Tests verify:
- Complete isolation between libraries and users (no cross-library or cross-user leaks).
- Authorization verification: unauthorized or non-existent library IDs are rejected.
- Empty libraries produce strictly 0 results without fallback to global search.
- Source provenance and freshness indicators (version, license, last_checked_at,
  freshness_status).
- 30-day age threshold correctly triggers 'not_recently_checked' without falsely
  claiming content changed.
- Backward compatibility: unscoped retrieval remains unaffected.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from ezo_api.db.base import utcnow
from ezo_api.db.models import (
    DocumentRevision,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeLibrary,
    KnowledgeSource,
    LearnedSource,
    User,
)
from ezo_api.knowledge.retrieval.retriever import Retriever
from ezo_api.learning.service import resolve_library_documents
from ezo_api.tools.base import ToolContext
from ezo_api.tools.research_tools import KnowledgeSearchArgs, KnowledgeSearchTool


def _make_mock_retriever() -> Retriever:
    mock_embeddings = MagicMock()
    mock_embeddings.available = False
    mock_vectors = MagicMock()
    return Retriever(embeddings=mock_embeddings, vectors=mock_vectors)


@pytest.mark.anyio
async def test_resolve_library_documents_cross_user_and_isolation(database_url: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url.replace("sqlite:///", "sqlite+aiosqlite:///"))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as session:
        user_a = User(email="a@ezo.uz", display_name="User A")
        user_b = User(email="b@ezo.uz", display_name="User B")
        session.add_all([user_a, user_b])
        await session.flush()

        # Library A for User A, Library B for User B, Library A2 for User A
        lib_a = KnowledgeLibrary(user_id=user_a.id, name="Library A", description="")
        lib_a2 = KnowledgeLibrary(user_id=user_a.id, name="Library A2", description="")
        lib_b = KnowledgeLibrary(user_id=user_b.id, name="Library B", description="")
        session.add_all([lib_a, lib_a2, lib_b])
        await session.flush()

        # Learned source in Lib A
        ks_a = KnowledgeSource(user_id=user_a.id, name="Source A", source_type="learned")
        session.add(ks_a)
        await session.flush()
        ls_a = LearnedSource(
            user_id=user_a.id,
            library_id=lib_a.id,
            knowledge_source_id=ks_a.id,
            kind="website",
            target="https://example.com/a",
            title="Doc A Title",
            status="indexed",
            limits={},
            stats={},
        )
        doc_a = KnowledgeDocument(
            user_id=user_a.id,
            source_id=ks_a.id,
            title="Doc A",
            status="indexed",
            mime_type="text/plain",
            size_bytes=100,
            content_hash="hash_a",
        )
        session.add_all([ls_a, doc_a])
        await session.flush()
        rev_a = DocumentRevision(
            document_id=doc_a.id, revision_number=1, content_hash="hash_a", raw_text="A"
        )
        session.add(rev_a)
        await session.flush()
        doc_a.current_revision_id = rev_a.id

        # Learned source in Lib B
        ks_b = KnowledgeSource(user_id=user_b.id, name="Source B", source_type="learned")
        session.add(ks_b)
        await session.flush()
        ls_b = LearnedSource(
            user_id=user_b.id,
            library_id=lib_b.id,
            knowledge_source_id=ks_b.id,
            kind="website",
            target="https://example.com/b",
            title="Doc B Title",
            status="indexed",
            limits={},
            stats={},
        )
        doc_b = KnowledgeDocument(
            user_id=user_b.id,
            source_id=ks_b.id,
            title="Doc B",
            status="indexed",
            mime_type="text/plain",
            size_bytes=100,
            content_hash="hash_b",
        )
        session.add_all([ls_b, doc_b])
        await session.flush()
        rev_b = DocumentRevision(
            document_id=doc_b.id, revision_number=1, content_hash="hash_b", raw_text="B"
        )
        session.add(rev_b)
        await session.flush()
        doc_b.current_revision_id = rev_b.id

        await session.commit()

        # 1. User A resolves Library A -> gets doc_a.id only
        lib, doc_ids = await resolve_library_documents(
            session, user_id=user_a.id, library_id=lib_a.id
        )
        assert lib.id == lib_a.id
        assert doc_ids == frozenset([doc_a.id])
        assert doc_b.id not in doc_ids

        # 2. User A resolves Empty Library A2 -> gets empty frozenset
        lib2, doc_ids2 = await resolve_library_documents(
            session, user_id=user_a.id, library_id=lib_a2.id
        )
        assert lib2.id == lib_a2.id
        assert doc_ids2 == frozenset()

        # 3. User A attempts to access User B's Library B -> 403 Forbidden
        with pytest.raises(HTTPException) as exc_info:
            await resolve_library_documents(session, user_id=user_a.id, library_id=lib_b.id)
        assert exc_info.value.status_code == 403

        # 4. Accessing non-existent library -> 404 Not Found
        with pytest.raises(HTTPException) as exc_info404:
            await resolve_library_documents(session, user_id=user_a.id, library_id=uuid.uuid4())
        assert exc_info404.value.status_code == 404

    await engine.dispose()


@pytest.mark.anyio
async def test_retriever_empty_document_ids_short_circuit(database_url: str) -> None:
    """When document_ids is an empty frozenset, retriever must never fall back to global."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url.replace("sqlite:///", "sqlite+aiosqlite:///"))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as session:
        user = User(email="test@ezo.uz", display_name="Test")
        session.add(user)
        await session.flush()

        # Add a global searchable document for the user
        ks = KnowledgeSource(user_id=user.id, name="Manual Upload", source_type="upload")
        session.add(ks)
        await session.flush()
        doc = KnowledgeDocument(
            user_id=user.id,
            source_id=ks.id,
            title="Global Important Document",
            status="indexed",
            mime_type="text/plain",
            size_bytes=100,
            content_hash="hash_global",
        )
        session.add(doc)
        await session.flush()
        rev = DocumentRevision(
            document_id=doc.id,
            revision_number=1,
            content_hash="hash_global",
            raw_text="Global Text",
        )
        session.add(rev)
        await session.flush()
        doc.current_revision_id = rev.id
        chunk = KnowledgeChunk(
            user_id=user.id,
            document_id=doc.id,
            revision_id=rev.id,
            chunk_index=0,
            text="Global Text with keyword information",
        )
        session.add(chunk)
        await session.commit()

        retriever = _make_mock_retriever()

        # Retrieve with document_ids = frozenset() -> MUST return 0 sources
        result = await retriever.retrieve(
            session,
            user_id=user.id,
            query="keyword information",
            project_scope=None,
            document_ids=frozenset(),
        )
        assert len(result.sources) == 0
        assert result.mode == "none"

        # Unscoped retrieve without document_ids -> find global doc (backward compatibility)
        result_unscoped = await retriever.retrieve(
            session,
            user_id=user.id,
            query="keyword information",
            project_scope=None,
            document_ids=None,
        )
        assert len(result_unscoped.sources) > 0

    await engine.dispose()


@pytest.mark.anyio
async def test_provenance_and_freshness_logic(database_url: str) -> None:
    """Verifies version, license, last_checked_at and freshness status calculations."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url.replace("sqlite:///", "sqlite+aiosqlite:///"))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as session:
        user = User(email="fresh@ezo.uz", display_name="Freshness User")
        session.add(user)
        await session.flush()

        lib = KnowledgeLibrary(user_id=user.id, name="Test Lib", description="")
        session.add(lib)
        await session.flush()

        # Source 1: Current (< 30 days, content_changed False)
        ks1 = KnowledgeSource(user_id=user.id, name="FastAPI Docs", source_type="learned")
        session.add(ks1)
        await session.flush()
        recent_date = utcnow() - timedelta(days=5)
        ls1 = LearnedSource(
            user_id=user.id,
            library_id=lib.id,
            knowledge_source_id=ks1.id,
            kind="website",
            target="https://fastapi.tiangolo.com",
            title="FastAPI",
            status="indexed",
            version="0.115.0",
            license="MIT",
            last_checked_at=recent_date,
            stats={"content_changed": False},
            limits={},
        )
        doc1 = KnowledgeDocument(
            user_id=user.id,
            source_id=ks1.id,
            title="FastAPI Tutorial",
            status="indexed",
            mime_type="text/plain",
            size_bytes=100,
            content_hash="h1",
        )
        session.add_all([ls1, doc1])
        await session.flush()
        rev1 = DocumentRevision(
            document_id=doc1.id, revision_number=1, content_hash="h1", raw_text="FastAPI framework"
        )
        session.add(rev1)
        await session.flush()
        doc1.current_revision_id = rev1.id
        chunk1 = KnowledgeChunk(
            user_id=user.id,
            document_id=doc1.id,
            revision_id=rev1.id,
            chunk_index=0,
            text="FastAPI web framework",
        )
        session.add(chunk1)

        # Source 2: Changed (content_changed True)
        ks2 = KnowledgeSource(user_id=user.id, name="React Docs", source_type="learned")
        session.add(ks2)
        await session.flush()
        ls2 = LearnedSource(
            user_id=user.id,
            library_id=lib.id,
            knowledge_source_id=ks2.id,
            kind="website",
            target="https://react.dev",
            title="React",
            status="indexed",
            version="19.0.0",
            license="MIT",
            last_checked_at=recent_date,
            stats={"content_changed": True},
            limits={},
        )
        doc2 = KnowledgeDocument(
            user_id=user.id,
            source_id=ks2.id,
            title="React Hooks",
            status="indexed",
            mime_type="text/plain",
            size_bytes=100,
            content_hash="h2",
        )
        session.add_all([ls2, doc2])
        await session.flush()
        rev2 = DocumentRevision(
            document_id=doc2.id, revision_number=1, content_hash="h2", raw_text="React hooks"
        )
        session.add(rev2)
        await session.flush()
        doc2.current_revision_id = rev2.id
        chunk2 = KnowledgeChunk(
            user_id=user.id,
            document_id=doc2.id,
            revision_id=rev2.id,
            chunk_index=0,
            text="React hooks framework",
        )
        session.add(chunk2)

        # Source 3: Not recently checked (> 30 days)
        old_date = utcnow() - timedelta(days=45)
        ks3 = KnowledgeSource(user_id=user.id, name="Legacy Docs", source_type="learned")
        session.add(ks3)
        await session.flush()
        ls3 = LearnedSource(
            user_id=user.id,
            library_id=lib.id,
            knowledge_source_id=ks3.id,
            kind="website",
            target="https://legacy.example.com",
            title="Legacy",
            status="indexed",
            version="1.0.0",
            license="Apache-2.0",
            last_checked_at=old_date,
            stats={"content_changed": False},
            limits={},
        )
        doc3 = KnowledgeDocument(
            user_id=user.id,
            source_id=ks3.id,
            title="Legacy Guide",
            status="indexed",
            mime_type="text/plain",
            size_bytes=100,
            content_hash="h3",
        )
        session.add_all([ls3, doc3])
        await session.flush()
        rev3 = DocumentRevision(
            document_id=doc3.id, revision_number=1, content_hash="h3", raw_text="Legacy framework"
        )
        session.add(rev3)
        await session.flush()
        doc3.current_revision_id = rev3.id
        chunk3 = KnowledgeChunk(
            user_id=user.id,
            document_id=doc3.id,
            revision_id=rev3.id,
            chunk_index=0,
            text="Legacy framework guide",
        )
        session.add(chunk3)

        await session.commit()

        retriever = _make_mock_retriever()

        # Retrieve FastAPI -> check freshness_status == "current", version, license
        res1 = await retriever.retrieve(
            session, user.id, "FastAPI web framework", None, document_ids=frozenset([doc1.id])
        )
        assert len(res1.sources) == 1
        s1 = res1.sources[0]
        assert s1.version == "0.115.0"
        assert s1.license == "MIT"
        assert s1.freshness_status == "current"
        assert s1.last_checked_at is not None

        # Retrieve React -> check freshness_status == "changed"
        res2 = await retriever.retrieve(
            session, user.id, "React hooks", None, document_ids=frozenset([doc2.id])
        )
        assert len(res2.sources) == 1
        s2 = res2.sources[0]
        assert s2.freshness_status == "changed"
        assert "o'zgarganligi aniqlangan" in (s2.freshness_note or "")

        # Retrieve Legacy -> check freshness_status == "not_recently_checked"
        res3 = await retriever.retrieve(
            session, user.id, "Legacy framework guide", None, document_ids=frozenset([doc3.id])
        )
        assert len(res3.sources) == 1
        s3 = res3.sources[0]
        assert s3.freshness_status == "not_recently_checked"
        assert "30 kundan ortiq" in (s3.freshness_note or "")

    await engine.dispose()


@pytest.mark.anyio
async def test_knowledge_search_tool_library_scoping(database_url: str) -> None:
    """Verifies that KnowledgeSearchTool correctly honors ctx.library_scope and args.library_id."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url.replace("sqlite:///", "sqlite+aiosqlite:///"))
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with sessionmaker() as session:
        user = User(email="tool@ezo.uz", display_name="Tool User")
        other_user = User(email="other@ezo.uz", display_name="Other User")
        session.add_all([user, other_user])
        await session.flush()

        lib = KnowledgeLibrary(user_id=user.id, name="My Scoped Lib", description="")
        other_lib = KnowledgeLibrary(user_id=other_user.id, name="Other Lib", description="")
        session.add_all([lib, other_lib])
        await session.flush()

        ks = KnowledgeSource(user_id=user.id, name="Sample", source_type="learned")
        session.add(ks)
        await session.flush()
        ls = LearnedSource(
            user_id=user.id,
            library_id=lib.id,
            knowledge_source_id=ks.id,
            kind="website",
            target="https://example.org",
            title="Example",
            status="indexed",
            limits={},
            stats={},
        )
        doc = KnowledgeDocument(
            user_id=user.id,
            source_id=ks.id,
            title="Sample Doc",
            status="indexed",
            mime_type="text/plain",
            size_bytes=50,
            content_hash="h_tool",
        )
        session.add_all([ls, doc])
        await session.flush()
        rev = DocumentRevision(
            document_id=doc.id,
            revision_number=1,
            content_hash="h_tool",
            raw_text="Secret tool text",
        )
        session.add(rev)
        await session.flush()
        doc.current_revision_id = rev.id
        chunk = KnowledgeChunk(
            user_id=user.id,
            document_id=doc.id,
            revision_id=rev.id,
            chunk_index=0,
            text="Secret tool text keyword",
        )
        session.add(chunk)
        await session.commit()

        services = MagicMock()
        services.retriever = _make_mock_retriever()

        tool = KnowledgeSearchTool()

        # 1. Successful scoped search via context
        ctx = ToolContext(
            session=session,
            services=services,
            user_id=user.id,
            library_scope=lib.id,
        )
        res = await tool.run(KnowledgeSearchArgs(query="Secret tool text keyword"), ctx)
        assert res.ok is True
        assert len(res.sources) == 1
        assert res.sources[0].title == "Sample Doc"

        # 2. Denied search when scoping to other user's library -> ok=False, no fallback
        ctx_unauth = ToolContext(
            session=session,
            services=services,
            user_id=user.id,
            library_scope=other_lib.id,
        )
        res_unauth = await tool.run(
            KnowledgeSearchArgs(query="Secret tool text keyword"), ctx_unauth
        )
        assert res_unauth.ok is False
        assert len(res_unauth.sources) == 0
        assert "Forbidden" in (res_unauth.error or "")

    await engine.dispose()
