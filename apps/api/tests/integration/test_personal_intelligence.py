"""Integration tests for Personal Intelligence K9: consent, goals, profile, export, and tenant isolation."""

from __future__ import annotations

import uuid
from httpx import AsyncClient
from sqlalchemy import select

from ezo_api.db.models import Memory, PersonalGoal, User
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


async def test_personal_profile_returns_intelligence_metadata(client: AsyncClient) -> None:
    response = await client.get("/api/personal/profile")
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "email" in data
    assert "memory_stats" in data
    assert "goals_stats" in data
    assert "learning_progress" in data
    assert data["memory_consent"] is False  # Privacy-first default: False!


async def test_explicit_memory_consent_grant_and_revoke(client: AsyncClient) -> None:
    # Initially False
    profile = (await client.get("/api/personal/profile")).json()
    assert profile["memory_consent"] is False

    # Grant consent
    grant_res = await client.post(
        "/api/personal/consent", json={"consent": True, "auto_memory": True}
    )
    assert grant_res.status_code == 200
    assert grant_res.json()["memory_consent"] is True
    assert grant_res.json()["auto_memory"] is True

    updated_profile = (await client.get("/api/personal/profile")).json()
    assert updated_profile["memory_consent"] is True
    assert updated_profile["auto_memory"] is True

    # Revoke consent
    revoke_res = await client.post(
        "/api/personal/consent", json={"consent": False, "auto_memory": False}
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["memory_consent"] is False
    assert revoke_res.json()["auto_memory"] is False

    final_profile = (await client.get("/api/personal/profile")).json()
    assert final_profile["memory_consent"] is False


async def test_memory_is_not_stored_without_explicit_consent(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    # Ensure consent is off
    await client.post("/api/personal/consent", json={"consent": False, "auto_memory": False})

    # Chat with a memorable fact
    await stream_chat(client, message="Eslab qol: mening sevimli mashg'ulotim kitob o'qish.")

    # Must NOT have stored memory
    memories = (await client.get("/api/memories")).json()
    assert len(memories) == 0


async def test_memory_is_stored_when_consent_is_granted(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    # Grant explicit consent
    await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})

    # Chat with memorable statement
    await stream_chat(client, message="Eslab qol: men Toshkentda yashayman.")

    memories = (await client.get("/api/memories")).json()
    assert len(memories) >= 1
    assert any("Toshkentda yashayman" in m["content"] for m in memories)


async def test_personal_goals_crud(client: AsyncClient) -> None:
    # 1. Create Goal
    create_res = await client.post(
        "/api/personal/goals",
        json={
            "title": "IELTS 7.5 olish",
            "description": "2026 yil oxirigacha IELTS Speaking 7.5 ga chiqish",
            "category": "language",
            "progress": 0.25,
            "metadata": {"target_band": 7.5, "part": "speaking"},
        },
    )
    assert create_res.status_code == 201
    goal = create_res.json()
    goal_id = goal["id"]
    assert goal["title"] == "IELTS 7.5 olish"
    assert goal["progress"] == 0.25
    assert goal["status"] == "active"

    # 2. List Goals
    list_res = await client.get("/api/personal/goals")
    assert list_res.status_code == 200
    assert any(g["id"] == goal_id for g in list_res.json())

    # 3. Update Goal
    update_res = await client.patch(
        f"/api/personal/goals/{goal_id}",
        json={"progress": 1.0, "description": "Maqsad to'liq bajarildi!"},
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["progress"] == 1.0
    assert updated["status"] == "completed"

    # 4. Filter by status
    filtered_res = await client.get("/api/personal/goals?status=completed")
    assert any(g["id"] == goal_id for g in filtered_res.json())

    # 5. Delete Goal
    del_res = await client.delete(f"/api/personal/goals/{goal_id}")
    assert del_res.status_code == 204

    # Verify deleted
    after_del = await client.get(f"/api/personal/goals?status=completed")
    assert not any(g["id"] == goal_id for g in after_del.json())


async def test_personal_memories_export(client: AsyncClient) -> None:
    # Add manual memory
    await client.post(
        "/api/memories",
        json={"content": "Python va TypeScript dasturchisi", "category": "personal", "importance": 0.9},
    )

    export_res = await client.get("/api/personal/memories/export")
    assert export_res.status_code == 200
    data = export_res.json()
    assert data["total_memories"] >= 1
    assert "markdown" in data
    assert "# EZO OS — Shaxsiy Xotira Eksporti" in data["markdown"]
    assert "Python va TypeScript dasturchisi" in data["markdown"]

    # Also test /api/memories/export endpoint
    direct_export = await client.get("/api/memories/export")
    assert direct_export.status_code == 200
    assert direct_export.json()["total_memories"] >= 1


async def test_tenant_isolation_memories_and_goals(
    client: AsyncClient, app
) -> None:
    """Ensure User A cannot view, mutate or delete User B's memories or goals."""
    async with app.state.services.db.sessionmaker() as session:
        # Create user B
        other_user = User(
            id=uuid.uuid4(),
            email="victim@example.com",
            display_name="Victim User",
            preferences={"memory_consent": True},
        )
        session.add(other_user)
        await session.flush()

        # Create memory for user B
        other_memory = Memory(
            user_id=other_user.id,
            memory_type="profile",
            category="personal",
            content="Maxfiy shaxsiy ma'lumot (User B)",
            source="user",
            importance=0.9,
        )
        session.add(other_memory)

        # Create goal for user B
        other_goal = PersonalGoal(
            user_id=other_user.id,
            title="User B shaxsiy maqsadi",
            category="career",
            progress=0.5,
        )
        session.add(other_goal)
        await session.commit()
        other_memory_id = other_memory.id
        other_goal_id = other_goal.id

    # User A accesses endpoints:
    # 1. User A lists memories -> other_memory must NOT appear
    mem_list = (await client.get("/api/memories")).json()
    assert not any(m["id"] == str(other_memory_id) for m in mem_list)

    # 2. User A tries to update other_memory -> 404
    upd_mem = await client.patch(f"/api/memories/{other_memory_id}", json={"importance": 0.1})
    assert upd_mem.status_code == 404

    # 3. User A tries to delete other_memory -> 404
    del_mem = await client.delete(f"/api/memories/{other_memory_id}")
    assert del_mem.status_code == 404

    # 4. User A exports memories -> other_memory must NOT appear
    export_mem = (await client.get("/api/personal/memories/export")).json()
    assert not any(m["id"] == str(other_memory_id) for m in export_mem["memories"])
    assert "User B" not in export_mem["markdown"]

    # 5. User A lists goals -> other_goal must NOT appear
    goals_list = (await client.get("/api/personal/goals")).json()
    assert not any(g["id"] == str(other_goal_id) for g in goals_list)

    # 6. User A tries to update other_goal -> 404
    upd_goal = await client.patch(f"/api/personal/goals/{other_goal_id}", json={"progress": 0.9})
    assert upd_goal.status_code == 404

    # 7. User A tries to delete other_goal -> 404
    del_goal = await client.delete(f"/api/personal/goals/{other_goal_id}")
    assert del_goal.status_code == 404
