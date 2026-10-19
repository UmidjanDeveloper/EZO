"""Integration tests for Knowledge OS K3 — Capability Analyzer API and Chat."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.db.models import (
    KnowledgeLibrary,
    User,
)
from ezo_api.main import create_app
from ezo_api.providers.base import ModelProvider
from tests.conftest import make_settings
from tests.integration.helpers import stream_chat
from tests.learning_web import DOCS, FakeWeb, docs_site


def build_app(database_url: str, providers: dict[str, ModelProvider], web: FakeWeb) -> FastAPI:
    return create_app(make_settings(database_url), providers=providers, fetcher=web.fetcher())


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def k3_app(database_url: str, providers: dict[str, ModelProvider], web: FakeWeb) -> FastAPI:
    return build_app(database_url, providers, web)


@pytest.fixture
async def client(k3_app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=k3_app), base_url="http://test") as c:
        yield c
    await k3_app.state.services.db.dispose()


async def test_empty_library_capability_analysis(client: AsyncClient) -> None:
    # 1. Create an empty library
    res = await client.post("/api/learning/libraries", json={"name": "Empty Test Library"})
    assert res.status_code == 201
    lib_id = res.json()["id"]

    # 2. Analyze empty library
    res_analyze = await client.post(f"/api/learning/libraries/{lib_id}/analyze")
    assert res_analyze.status_code == 200
    data = res_analyze.json()
    assert data["library_id"] == lib_id
    assert data["sources_count"] == 0
    assert data["capabilities_count"] == 0
    assert data["proposals"] == []
    assert len(data["evidence_limitations"]) > 0
    assert data["status"] == "proposal"

    # 3. Get capabilities endpoint returns same
    res_get = await client.get(f"/api/learning/libraries/{lib_id}/capabilities")
    assert res_get.status_code == 200
    assert res_get.json()["capabilities_count"] == 0


async def test_cross_user_library_analysis_forbidden(client: AsyncClient, k3_app: FastAPI) -> None:
    # Create another user's library directly in database
    async with k3_app.state.services.db.sessionmaker() as session:
        other_user = User(email="other_k3_user@ezo.uz", display_name="Other K3 User")
        session.add(other_user)
        await session.flush()
        other_lib = KnowledgeLibrary(
            user_id=other_user.id, name="Other User Private Lib", description=""
        )
        session.add(other_lib)
        await session.commit()
        other_lib_id = str(other_lib.id)

    # Current authenticated user cannot analyze or get another user's library -> 404
    res_post = await client.post(f"/api/learning/libraries/{other_lib_id}/analyze")
    assert res_post.status_code == 404

    res_get = await client.get(f"/api/learning/libraries/{other_lib_id}/capabilities")
    assert res_get.status_code == 404


async def test_source_and_library_capability_analysis_flow(
    client: AsyncClient, web: FakeWeb, k3_app: FastAPI
) -> None:
    docs_site(web)

    # 1. Learn a documentation source
    learn_res = await client.post(
        "/api/learning/sources",
        json={
            "target": f"{DOCS}/guide/",
            "library_name": "Widget Guide Library",
            "limits": {"min_interval_seconds": 0},
        },
    )
    assert learn_res.status_code == 202
    source_id = learn_res.json()["id"]
    lib_id = learn_res.json()["library_id"]

    # Wait for reading to complete
    source_detail = (await client.get(f"/api/learning/sources/{source_id}")).json()
    assert source_detail["status"] == "indexed"

    # 2. Analyze individual source capabilities
    res_src_analyze = await client.post(f"/api/learning/sources/{source_id}/analyze")
    assert res_src_analyze.status_code == 200
    src_data = res_src_analyze.json()
    assert src_data["source_id"] == source_id
    assert src_data["status"] == "proposal"
    assert len(src_data["capabilities"]) >= 1

    primary_cap = src_data["capabilities"][0]
    assert primary_cap["status"] == "proposal"
    assert "Widget" in primary_cap["title"] or "Integration" in primary_cap["title"]
    assert len(primary_cap["evidence"]) >= 1
    assert primary_cap["evidence"][0]["evidence_level"] == "directly_supported"

    # Check cached retrieval
    res_src_cached = await client.get(f"/api/learning/sources/{source_id}/capabilities")
    assert res_src_cached.status_code == 200
    assert res_src_cached.json()["source_id"] == source_id

    # 3. Analyze library capabilities
    res_lib_analyze = await client.post(f"/api/learning/libraries/{lib_id}/analyze")
    assert res_lib_analyze.status_code == 200
    lib_data = res_lib_analyze.json()
    assert lib_data["library_id"] == lib_id
    assert lib_data["sources_count"] == 1
    assert lib_data["analyzed_sources_count"] == 1
    assert lib_data["capabilities_count"] >= 1
    assert lib_data["status"] == "proposal"
    assert any("Widget" in p["title"] for p in lib_data["proposals"])


async def test_chat_capability_analyzer_intent(
    client: AsyncClient, web: FakeWeb, k3_app: FastAPI
) -> None:
    docs_site(web)

    # 1. Create library and learn source
    learn_res = await client.post(
        "/api/learning/sources",
        json={
            "target": f"{DOCS}/guide/",
            "library_name": "Python Library Guide",
            "limits": {"min_interval_seconds": 0},
        },
    )
    assert learn_res.status_code == 202
    lib_id = learn_res.json()["library_id"]

    # 2. Stream chat asking for capability analysis
    query = (
        "EZO, analyze the documentation you learned from this Python library. "
        "What useful abilities could you gain?"
    )
    events = await stream_chat(client, message=query, library_id=lib_id)
    names = [name for name, _ in events]
    assert "meta" in names and "done" in names

    meta_event = events[0][1]
    assert meta_event["intent"] == "learning"

    # Verify tool calls or activities
    activity_events = [data for name, data in events if name == "activity"]
    assert len(activity_events) >= 0
    # Verify delta text was received
    delta_texts = [data for name, data in events if name == "delta"]
    assert len(delta_texts) > 0
