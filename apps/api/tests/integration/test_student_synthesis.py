"""Multi-source scope and model output validation, using deterministic fake providers."""

import hashlib
import json
import uuid

import pytest
from sqlalchemy import select

from ezo_api.db.models import KnowledgeChunk
from ezo_api.student.ingestion import StudentIngestion
from tests.integration.test_student_v1 import DATA, extracted


async def sources(client, app):
    docs = []
    for i in range(2):
        raw = DATA + str(i).encode()
        job = (await client.post("/api/student/uploads?filename=book.pdf", content=raw)).json()
        jobs = StudentIngestion(app.state.services.db)
        result = extracted(raw)
        assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
        await jobs.publish_extraction(await jobs.claim("test"), result)
        docs.append(job["document_id"])
    return {"document_ids": docs, "question": "Fotosintez", "kind": "comparison"}


async def test_comparison_requires_all_selected_citations_and_context_is_data_only(
    client,
    app,
    fake_anthropic,
):
    body = await sources(client, app)
    fake_anthropic.reply = "Manbalar quyosh energiyasini ta’riflaydi [1][2]."
    r = await client.post("/api/student/synthesize", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["generated"] and len(r.json()["citations"]) == 2
    assert {c["document_id"] for c in r.json()["citations"]} == set(body["document_ids"])
    assert r.json()["verification"] == "source_identity_and_quotes_only"
    for text in ["Claim [1]", "Claim [1][2][999]", "No references"]:
        fake_anthropic.reply = text
        assert (await client.post("/api/student/synthesize", json=body)).status_code == 502
    context = await client.post("/api/student/context", json=body)
    assert context.status_code == 200, context.text
    assert context.json()["action_authority"] == "none"
    assert len(context.json()["nodes"]) == 2
    assert all(n["metadata"]["trust"] == "untrusted_source_data" for n in context.json()["nodes"])
    assert all(
        n["metadata"]["provenance"]["extra"]["offset_unit"] == "unicode_codepoints"
        for n in context.json()["nodes"]
    )


async def test_unauthorized_scope_rejected_before_any_model_request(client, app, fake_openai):
    body = await sources(client, app)
    fake_openai.requests.clear()
    before = fake_openai.embed_calls
    body["document_ids"][1] = str(uuid.uuid4())
    r = await client.post("/api/student/synthesize", json=body)
    assert r.status_code == 404
    assert fake_openai.requests == []
    assert fake_openai.embed_calls == before
    assert (
        await client.post("/api/student/context", json={**body, "project_id": str(uuid.uuid4())})
    ).status_code == 404


@pytest.mark.parametrize("mutation", ["quote", "edge", "duplicate", "extra", "source"])
async def test_graph_malformed_evidence_rejected(client, app, fake_anthropic, mutation):
    body = {**(await sources(client, app)), "kind": "concept_graph"}
    graph = {
        "nodes": [{"id": "sun", "label": "Quyosh", "source": 1, "quote": "quyosh energiyasini"}],
        "edges": [],
    }
    if mutation == "quote":
        graph["nodes"][0]["quote"] = "invented quote"
    if mutation == "source":
        graph["nodes"][0]["source"] = 8
    if mutation == "duplicate":
        graph["nodes"].append(graph["nodes"][0])
    if mutation == "extra":
        graph["execute"] = "install skill"
    if mutation == "edge":
        graph["edges"].append(
            {"start": "sun", "end": "unknown", "label": "feeds", "source": 1, "quote": "quyosh"}
        )
    fake_anthropic.reply = json.dumps(graph)
    r = await client.post("/api/student/synthesize", json=body)
    assert r.status_code == 502, r.text


async def test_graph_valid_quotes_and_tainted_chunk_rejected(client, app, fake_anthropic):
    body = {**(await sources(client, app)), "kind": "concept_graph"}
    fake_anthropic.reply = json.dumps(
        {
            "nodes": [
                {"id": "sun", "label": "Quyosh", "source": 1, "quote": "quyosh energiyasini"}
            ],
            "edges": [],
        }
    )
    r = await client.post("/api/student/synthesize", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["graph"]["nodes"][0]["id"] == "sun"
    async with app.state.services.db.sessionmaker() as session:
        chunks = (await session.scalars(select(KnowledgeChunk))).all()
        for chunk in chunks:
            chunk.text = "Fotosintez invented text"
        await session.commit()
    r = await client.post("/api/student/synthesize", json=body)
    assert r.status_code == 200 and r.json()["status"] == "insufficient_evidence"
    assert r.json()["generated"] is False


async def test_comparison_distinct_sources_and_offline_never_fake(client, app):
    body = await sources(client, app)
    one = {**body, "document_ids": [body["document_ids"][0]] * 2}
    assert (await client.post("/api/student/synthesize", json=one)).status_code == 422
    app.state.services.router.providers = {}
    assert (await client.post("/api/student/synthesize", json=body)).status_code == 503
    assert (
        await client.post(
            "/api/student/context", json={**body, "document_ids": body["document_ids"] * 3}
        )
    ).status_code == 422
