"""Runs only against PostgreSQL with the pgvector extension (EZO_TEST_DATABASE_URL)."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

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
