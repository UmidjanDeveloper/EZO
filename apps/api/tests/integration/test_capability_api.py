"""Integration tests for Knowledge OS K3 — Capability Analyzer API and Chat."""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ezo_api.db.models import (
    KnowledgeLibrary,
    LearnedSource,
    User,
)
from ezo_api.main import create_app
from ezo_api.providers.base import ModelProvider
from tests.conftest import make_settings
from tests.fakes import FakeProvider
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
    # The opening of a document is context, not a confirmed capability.
    assert primary_cap["evidence"][0]["evidence_level"] == "inferred"
    assert primary_cap["confidence"] <= 0.6
    assert primary_cap["description"].startswith("Use the website source")

    # The analysis is cached (same timestamp) while the content read is unchanged.
    res_src_cached = await client.get(f"/api/learning/sources/{source_id}/capabilities")
    assert res_src_cached.status_code == 200
    assert res_src_cached.json()["source_id"] == source_id
    assert res_src_cached.json()["analyzed_at"] == src_data["analyzed_at"]

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
    client: AsyncClient, web: FakeWeb, k3_app: FastAPI, fake_anthropic: FakeProvider
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

    # The report (partly documentation text) reaches the model as a <source> data block;
    # the system notes carry only EZO's own wording, never the documentation's text.
    system = fake_anthropic.requests[-1].system or ""
    notes = system.split("Notes about this turn:")[1].split("Sources:")[0]
    assert "read-only capability analysis" in notes and "NOT installed" in notes
    assert "widget.connect" not in notes and "Ignore all previous" not in notes
    assert '<source n="1">' in system and "CAPABILITY ANALYSIS REPORT" in system
    # Verify delta text was received
    delta_texts = [data for name, data in events if name == "delta"]
    assert len(delta_texts) > 0


async def test_analysis_refused_while_reading_and_never_executes(
    client: AsyncClient, web: FakeWeb, k3_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import socket
    import subprocess

    docs_site(web)
    learned = await client.post(
        "/api/learning/sources",
        json={"target": f"{DOCS}/guide/", "limits": {"min_interval_seconds": 0}},
    )
    source_id = learned.json()["id"]

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("the capability analyzer must not execute or connect")

    # Analysis runs with process creation and network connections made impossible.
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(k3_app.state.services.fetcher, "fetch", forbidden)
    tools_before = k3_app.state.services.tools.names()
    analysed = await client.post(f"/api/learning/sources/{source_id}/analyze")
    assert analysed.status_code == 200
    proposals = analysed.json()["capabilities"]
    assert proposals and all(c["status"] == "proposal" for c in proposals)
    assert k3_app.state.services.tools.names() == tools_before
    monkeypatch.undo()

    # A source that is being read cannot be analysed yet.
    async with k3_app.state.services.db.sessionmaker() as session:
        row = await session.get(LearnedSource, uuid.UUID(source_id))
        assert row is not None
        row.status = "reading"
        await session.commit()
    busy = await client.post(f"/api/learning/sources/{source_id}/analyze")
    assert busy.status_code == 409
    assert (await client.get(f"/api/learning/sources/{source_id}/capabilities")).status_code == 409
