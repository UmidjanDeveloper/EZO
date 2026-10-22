"""Generation produces source-validated proposals; saving is an explicit action."""

import json

import pytest
from sqlalchemy import select

from ezo_api.db.models import KnowledgeChunk
from tests.integration.test_student_study import source


async def test_flashcard_generation_requires_explicit_save(client, app, fake_anthropic):
    body, _ = await source(client, app)
    fake_anthropic.reply = json.dumps(
        {
            "items": [
                {
                    "front": "Nima saqlanadi?",
                    "back": "Quyosh energiyasi [2].",
                    "source": 2,
                    "quote": "quyosh energiyasini",
                }
            ]
        }
    )
    r = await client.post(
        f"/api/student/documents/{body['document_id']}/learn", json={"kind": "flashcards"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["persistence"] == "proposal_only_explicit_save_required"
    assert (await client.get("/api/student/cards")).json() == []
    saved = await client.post("/api/student/cards", json=r.json()["flashcards"][0])
    assert saved.status_code == 201, saved.text
    assert saved.json()["quote"] == "quyosh energiyasini"


@pytest.mark.parametrize(
    "changes",
    [
        {"quote": "invented"},
        {"source": 6},
        {"back": "No evidence"},
        {"back": "Claim [999]"},
        {"execute": "install"},
        {"front": "x" * 601},
    ],
)
async def test_invalid_flashcard_proposals_fail_closed(client, app, fake_anthropic, changes):
    body, _ = await source(client, app)
    item = {"front": "Question", "back": "Evidence [1]", "source": 1, "quote": "quyosh"}
    fake_anthropic.reply = json.dumps({"items": [{**item, **changes}]})
    r = await client.post(
        f"/api/student/documents/{body['document_id']}/learn", json={"kind": "flashcards"}
    )
    assert r.status_code == 502, r.text
    assert (await client.get("/api/student/cards")).json() == []


async def test_legacy_text_can_create_verified_card_without_native_worker(client, app):
    r = await client.post(
        "/api/student/readings",
        json={"text": "O‘zbekiston 🙂 Fotosintez energiya.", "title": "Text reading"},
    )
    assert r.status_code == 201, r.text
    async with app.state.services.db.sessionmaker() as session:
        chunk = await session.scalar(select(KnowledgeChunk))
        body = {
            "document_id": str(chunk.document_id),
            "revision_id": str(chunk.revision_id),
            "chunk_id": str(chunk.id),
            "front": "Q?",
            "back": "O‘zbekiston 🙂",
            "quote_start": 0,
            "quote_end": len("O‘zbekiston 🙂"),
        }
    r = await client.post("/api/student/cards", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["quote"] == "O‘zbekiston 🙂"
