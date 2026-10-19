"""Runs only against PostgreSQL with the pgvector extension (EZO_TEST_DATABASE_URL)."""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from ezo_api.db.models import User
from ezo_api.knowledge.vectorstores.base import VectorFilter, VectorRecord
from ezo_api.knowledge.vectorstores.pgvector_store import PgVectorStore
from tests.integration.helpers import count_vectors


async def test_pgvector_store_is_used_and_searchable(
    client: AsyncClient, app: FastAPI, database_url: str
) -> None:
    status = (await client.get("/api/knowledge/status")).json()
    if not database_url.startswith("postgresql") or status["vector_store"] != "pgvector":
        pytest.skip("needs PostgreSQL with pgvector")
    await client.post(
        "/api/knowledge/documents",
        files={"file": ("a.txt", b"Toshkent metrosi 1977-yilda ochilgan.")},
    )
    assert await count_vectors(app) == 1
    results = (
        await client.post("/api/knowledge/search", json={"query": "metro qachon ochilgan"})
    ).json()
    assert results["mode"] == "hybrid"
    assert "1977" in results["results"][0]["excerpt"]


async def test_pgvector_respects_document_owner_and_project_scope(
    app: FastAPI, database_url: str
) -> None:
    if not database_url.startswith("postgresql"):
        pytest.skip("requires real PostgreSQL vector operators")
    store = PgVectorStore()
    document, other_document, private_project = (uuid.uuid4() for _ in range(3))
    async with app.state.services.db.sessionmaker() as session:
        owner = User(email="vector-owner@test.invalid", display_name="Owner")
        other = User(email="vector-other@test.invalid", display_name="Other")
        session.add_all([owner, other])
        await session.flush()
        visible, outside, cross_user, project = (uuid.uuid4() for _ in range(4))
        await store.upsert(
            session,
            [
                VectorRecord(
                    "chunk", visible, owner.id, "scope-test", [1, 0], document_id=document
                ),
                VectorRecord(
                    "chunk", outside, owner.id, "scope-test", [1, 0], document_id=other_document
                ),
                VectorRecord(
                    "chunk", cross_user, other.id, "scope-test", [1, 0], document_id=document
                ),
                VectorRecord(
                    "chunk",
                    project,
                    owner.id,
                    "scope-test",
                    [1, 0],
                    document_id=document,
                    project_id=private_project,
                ),
            ],
        )
        where = VectorFilter(owner.id, "chunk", "scope-test", document_ids=frozenset({document}))
        hits = await store.search(session, [1, 0], where, 20)
        assert [hit.owner_id for hit in hits] == [visible]
        empty = VectorFilter(owner.id, "chunk", "scope-test", document_ids=frozenset())
        assert await store.search(session, [1, 0], empty, 20) == []
