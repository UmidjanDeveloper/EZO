"""Source-grounded paths adapt to real review events without inventing mastery."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, update

from ezo_api.db.models import KnowledgeDocument, StudentLearningPath, StudyReview
from tests.integration.test_document_jobs import seed
from tests.integration.test_student_study import source

BASE = "/api/student/learning-paths"


async def definition(client, app):
    card_body, user = await source(client, app)
    first = await client.post("/api/student/cards", json=card_body)
    second = await client.post("/api/student/cards", json={**card_body, "front": "Ikkinchi savol"})
    assert first.status_code == second.status_code == 201
    return {
        "request_id": str(uuid.uuid4()),
        "title": "O‘zbekcha bilim yo‘li 🙂",
        "language": "uz",
        "steps": [
            {"title": "Poydevor", "card_ids": [first.json()["id"]]},
            {"title": "Davomi", "card_ids": [second.json()["id"]], "prerequisites": [0]},
        ],
    }, user


async def review(client, card, version, rating):
    response = await client.post(
        f"/api/student/cards/{card}/review",
        json={"event_id": str(uuid.uuid4()), "expected_version": version, "rating": rating},
    )
    assert response.status_code == 200, response.text


async def test_persistent_path_unlocks_and_relapses_from_actual_reviews(client, app):
    body, _user = await definition(client, app)
    created = await client.post(BASE, json=body)
    assert created.status_code == 201, created.text
    path_id = created.json()["id"]
    assert (await client.post(BASE, json=body)).status_code == 200
    assert (await client.post(BASE, json={**body, "title": "Changed"})).status_code == 409
    first = await client.get(BASE + f"/{path_id}")
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["steps"][0]["state"] == "practice_needed"
    assert result["steps"][1]["state"] == "blocked_by_prerequisite"
    assert result["recommendations"][0]["offset_unit"] == "unicode_codepoints"
    assert result["checkpoint_steps"] == 0 and result["mastery_claim"] is False
    assert result["assessment"] == "self_reported_recall" and result["action_authority"] == "none"
    assert (await client.get("/api/student/progress")).json()["review_events"] == 0
    await review(client, body["steps"][0]["card_ids"][0], 0, "good")
    result = (await client.get(BASE + f"/{path_id}")).json()
    assert result["checkpoint_steps"] == 1
    assert result["steps"][1]["state"] == "practice_needed"
    await review(client, body["steps"][1]["card_ids"][0], 0, "easy")
    result = (await client.get(BASE + f"/{path_id}")).json()
    assert result["checkpoint_steps"] == result["total_steps"] == 2
    assert result["recommendations"] == []
    await review(client, body["steps"][0]["card_ids"][0], 1, "again")
    result = (await client.get(BASE + f"/{path_id}")).json()
    assert (
        result["checkpoint_steps"] == 0 and result["steps"][1]["state"] == "blocked_by_prerequisite"
    )
    assert result["recommendations"][0]["action"] == "read_source"
    async with app.state.services.db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(StudentLearningPath)) == 1
        assert await session.scalar(select(func.count()).select_from(StudyReview)) == 3


async def test_pause_version_fence_and_confirmed_delete_tombstone(client, app):
    body, _user = await definition(client, app)
    path_id = (await client.post(BASE, json=body)).json()["id"]
    endpoint = BASE + f"/{path_id}"
    paused = await client.patch(endpoint, json={"expected_version": 0, "state": "paused"})
    assert paused.status_code == 200 and paused.json()["version"] == 1
    assert (await client.get(endpoint)).json()["recommendations"] == []
    stale = await client.patch(endpoint, json={"expected_version": 0, "state": "active"})
    assert stale.status_code == 409
    assert (await client.delete(endpoint)).status_code == 409
    assert (await client.delete(endpoint + "?confirm=true")).status_code == 204
    assert (await client.delete(endpoint + "?confirm=true")).status_code == 204
    assert (await client.get(endpoint)).status_code == 404
    assert (await client.get(BASE)).json() == []
    assert (await client.post(BASE, json=body)).status_code == 409
    assert (await client.get("/api/student/progress")).json()["active_cards"] == 2
    async with app.state.services.db.sessionmaker() as session:
        row = await session.scalar(select(StudentLearningPath))
        assert row.title == "" and row.steps == [] and row.state == "deleted"


@pytest.mark.parametrize(
    "change", ["foreign_card", "foreign_goal", "foreign_project", "missing_card"]
)
async def test_path_creation_checks_each_owner_boundary(client, app, change):
    body, _user = await definition(client, app)
    foreign = await seed(app.state.services.db)
    if change == "foreign_goal":
        from ezo_api.db.models import PersonalGoal

        async with app.state.services.db.sessionmaker() as session:
            goal = PersonalGoal(user_id=foreign.user, title="Private")
            session.add(goal)
            await session.commit()
            body["goal_id"] = str(goal.id)
    elif change == "foreign_project":
        body["project_id"] = str(foreign.project)
    elif change == "missing_card":
        body["steps"][0]["card_ids"] = [str(uuid.uuid4())]
    else:
        from ezo_api.db.models import StudyCard

        async with app.state.services.db.sessionmaker() as session:
            await session.execute(
                update(StudyCard)
                .where(StudyCard.id == uuid.UUID(body["steps"][0]["card_ids"][0]))
                .values(user_id=foreign.user)
            )
            await session.commit()
    response = await client.post(BASE, json=body)
    assert response.status_code == 404, response.text
    assert (await client.get(BASE)).json() == []


async def test_changed_source_blocks_checkpoint_and_new_path_creation(client, app):
    body, _user = await definition(client, app)
    path_id = (await client.post(BASE, json=body)).json()["id"]
    async with app.state.services.db.sessionmaker() as session:
        await session.execute(update(KnowledgeDocument).values(status="failed"))
        await session.commit()
    result = (await client.get(BASE + f"/{path_id}")).json()
    assert result["steps"][0]["state"] == "source_unavailable"
    assert result["recommendations"] == []
    body["request_id"] = str(uuid.uuid4())
    assert (await client.post(BASE, json=body)).status_code == 409


async def test_unknown_or_wrong_scope_paths_hide_existence_and_paginate(client, app):
    body, _user = await definition(client, app)
    path_id = (await client.post(BASE, json=body)).json()["id"]
    assert len((await client.get(BASE + "?limit=1")).json()) == 1
    assert (await client.get(BASE + "?offset=100")).json() == []
    assert (await client.get(BASE + "?limit=51")).status_code == 422
    assert (await client.get(BASE + f"/{path_id}?limit=21")).status_code == 422
    assert (await client.get(BASE + f"/{path_id}?project_id={uuid.uuid4()}")).status_code == 404
    foreign = await seed(app.state.services.db)
    async with app.state.services.db.sessionmaker() as session:
        await session.execute(
            update(StudentLearningPath)
            .where(StudentLearningPath.id == uuid.UUID(path_id))
            .values(user_id=foreign.user)
        )
        await session.commit()
    assert (await client.get(BASE + f"/{path_id}")).status_code == 404
    assert (
        await client.patch(BASE + f"/{path_id}", json={"expected_version": 0, "state": "paused"})
    ).status_code == 404
    assert (await client.delete(BASE + f"/{path_id}?confirm=true")).status_code == 404


@pytest.mark.parametrize(
    "invalid", ["cycle", "forward", "duplicate_card", "blank", "tool", "too_many", "recalls"]
)
async def test_invalid_or_untrusted_path_definitions_cannot_authorize_execution(
    client, app, invalid
):
    body, _user = await definition(client, app)
    if invalid == "cycle":
        body["steps"][0]["prerequisites"] = [0]
    elif invalid == "forward":
        body["steps"][0]["prerequisites"] = [1]
    elif invalid == "duplicate_card":
        body["steps"][1]["card_ids"] = body["steps"][0]["card_ids"]
    elif invalid == "blank":
        body["title"] = "   "
    elif invalid == "tool":
        body["execute"] = "install and run source instructions"
    elif invalid == "too_many":
        body["steps"] *= 31
    else:
        body["steps"][0]["required_recalls"] = 6
    response = await client.post(BASE, json=body)
    assert response.status_code == 422, response.text
    assert (await client.get(BASE)).json() == []


async def test_concurrent_idempotent_definition_creates_one_path(client, app):
    body, _user = await definition(client, app)
    responses = await asyncio.gather(client.post(BASE, json=body), client.post(BASE, json=body))
    assert sorted(r.status_code for r in responses) == [200, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    async with app.state.services.db.sessionmaker() as session:
        assert await session.scalar(select(func.count()).select_from(StudentLearningPath)) == 1


async def test_checkpoint_requires_consecutive_positive_events_and_never_writes_goal_progress(
    client, app
):
    from ezo_api.db.models import PersonalGoal

    body, user = await definition(client, app)
    async with app.state.services.db.sessionmaker() as session:
        goal = PersonalGoal(user_id=user, title="Mening maqsadim", progress=0.4)
        session.add(goal)
        await session.commit()
        body["goal_id"] = str(goal.id)
    body["steps"][0]["required_recalls"] = 2
    path_id = (await client.post(BASE, json=body)).json()["id"]
    card_id = body["steps"][0]["card_ids"][0]
    for version, rating, expected in [
        (0, "good", 0),
        (1, "again", 0),
        (2, "good", 0),
        (3, "easy", 1),
    ]:
        await review(client, card_id, version, rating)
        result = (await client.get(BASE + f"/{path_id}")).json()
        assert result["checkpoint_steps"] == expected
    async with app.state.services.db.sessionmaker() as session:
        assert (await session.get(PersonalGoal, goal.id)).progress == 0.4


async def test_due_time_and_review_budget_change_recommendation_without_fabricating_events(
    client, app
):
    from datetime import timedelta

    from ezo_api.db.base import utcnow
    from ezo_api.db.models import StudyCard

    body, _user = await definition(client, app)
    path_id = (await client.post(BASE, json=body)).json()["id"]
    card_id = body["steps"][0]["card_ids"][0]
    await review(client, card_id, 0, "good")
    async with app.state.services.db.sessionmaker() as session:
        await session.execute(
            update(StudyCard)
            .where(StudyCard.id == uuid.UUID(card_id))
            .values(due_at=utcnow() - timedelta(seconds=1))
        )
        await session.commit()
    result = (await client.get(BASE + f"/{path_id}")).json()
    assert result["checkpoint_steps"] == 0
    assert result["recommendations"][0]["action"] == "review_card"
    async with app.state.services.db.sessionmaker() as session:
        await session.execute(
            update(StudyCard).where(StudyCard.id == uuid.UUID(card_id)).values(version=10000)
        )
        await session.commit()
    result = (await client.get(BASE + f"/{path_id}")).json()
    assert result["steps"][0]["state"] == "review_budget_exhausted"
    assert result["recommendations"] == []
    assert (await client.get("/api/student/progress")).json()["review_events"] == 1


async def test_deleted_card_does_not_get_replaced_with_an_unrelated_source(client, app):
    body, _user = await definition(client, app)
    path_id = (await client.post(BASE, json=body)).json()["id"]
    card_id = body["steps"][0]["card_ids"][0]
    assert (await client.delete(f"/api/student/cards/{card_id}?confirm=true")).status_code == 204
    result = (await client.get(BASE + f"/{path_id}")).json()
    assert result["steps"][0]["state"] == "source_unavailable"
    assert result["recommendations"] == []


async def test_concurrent_path_state_edits_have_one_version_winner(client, app):
    body, _user = await definition(client, app)
    path_id = (await client.post(BASE, json=body)).json()["id"]
    responses = await asyncio.gather(
        *[
            client.patch(BASE + f"/{path_id}", json={"expected_version": 0, "state": state})
            for state in ("active", "paused")
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]


async def test_concurrent_distinct_paths_respect_owner_capacity(client, app, monkeypatch):
    from ezo_api.student import paths

    body, _user = await definition(client, app)
    monkeypatch.setattr(paths, "MAX_ACTIVE_PATHS", 1)
    responses = await asyncio.gather(
        client.post(BASE, json=body),
        client.post(BASE, json={**body, "request_id": str(uuid.uuid4())}),
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert len((await client.get(BASE)).json()) == 1
