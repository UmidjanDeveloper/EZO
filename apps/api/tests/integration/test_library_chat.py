from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient

from ezo_api.db.models import KnowledgeLibrary, User
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


async def create_library(client: AsyncClient, name: str, description: str = "") -> dict[str, Any]:
    response = await client.post(
        "/api/learning/libraries", json={"name": name, "description": description}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_chat_stream_with_library_selection(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    # 1. Create a library
    lib = await create_library(client, name="FastAPI Guide")
    lib_id = lib["id"]

    # 2. Start stream chat scoped to this library
    events = await stream_chat(client, message="FastAPI qanday ishlaydi?", library_id=lib_id)
    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done"

    meta = events[0][1]
    assert meta["library_id"] == lib_id
    assert meta["library_name"] == "FastAPI Guide"
    conv_id = meta["conversation_id"]

    # 3. Check conversation persisted library_id
    conv = (await client.get(f"/api/conversations/{conv_id}")).json()
    assert conv["library_id"] == lib_id

    # 4. Continuity: Next turn in same conversation inherits library_id automatically
    events2 = await stream_chat(client, message="Davom et", conversation_id=conv_id)
    meta2 = events2[0][1]
    assert meta2["library_id"] == lib_id
    assert meta2["library_name"] == "FastAPI Guide"

    # 5. Switching libraries in the same conversation
    lib2 = await create_library(client, name="React Guide")
    lib2_id = lib2["id"]
    events3 = await stream_chat(
        client, message="Endi React haqida", conversation_id=conv_id, library_id=lib2_id
    )
    meta3 = events3[0][1]
    assert meta3["library_id"] == lib2_id
    assert meta3["library_name"] == "React Guide"

    conv_switched = (await client.get(f"/api/conversations/{conv_id}")).json()
    assert conv_switched["library_id"] == lib2_id

    # 6. Clearing library: clear_library=True
    events4 = await stream_chat(
        client, message="Umumiy savol", conversation_id=conv_id, clear_library=True
    )
    meta4 = events4[0][1]
    assert meta4["library_id"] is None
    assert meta4.get("library_name") is None

    conv_cleared = (await client.get(f"/api/conversations/{conv_id}")).json()
    assert conv_cleared["library_id"] is None


async def test_non_streaming_chat_with_library(client: AsyncClient) -> None:
    lib = await create_library(client, name="Python Library")
    lib_id = lib["id"]

    res = await client.post("/api/chat", json={"message": "Python nima?", "library_id": lib_id})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["library_id"] == lib_id
    conv_id = data["conversation_id"]

    conv = (await client.get(f"/api/conversations/{conv_id}")).json()
    assert conv["library_id"] == lib_id


async def test_cross_user_library_rejection_in_chat(client: AsyncClient, app: Any) -> None:
    # Create another user and library in the database directly
    async with app.state.services.db.sessionmaker() as session:
        other_user = User(email="other_owner@ezo.uz", display_name="Other Owner")
        session.add(other_user)
        await session.flush()
        other_lib = KnowledgeLibrary(user_id=other_user.id, name="Secret Other Lib", description="")
        session.add(other_lib)
        await session.commit()
        other_lib_id = str(other_lib.id)

    # Authenticated test client attempts to stream chat with other user's library -> 403 Forbidden
    res = await client.post(
        "/api/chat/stream", json={"message": "Hack", "library_id": other_lib_id}
    )
    assert res.status_code == 403

    # Authenticated test client attempts non-streaming chat with other user's library -> 403
    res_non_stream = await client.post(
        "/api/chat", json={"message": "Hack", "library_id": other_lib_id}
    )
    assert res_non_stream.status_code == 403

    # Non-existent library -> 404 Not Found
    random_id = str(uuid.uuid4())
    res_404 = await client.post(
        "/api/chat/stream", json={"message": "Test", "library_id": random_id}
    )
    assert res_404.status_code == 404


async def test_conversation_update_library_authorization(client: AsyncClient, app: Any) -> None:
    # Create conversation for current user
    chat_res = await client.post("/api/chat", json={"message": "Initial message"})
    conv_id = chat_res.json()["conversation_id"]

    # Create library for current user
    lib = await create_library(client, name="User Lib")
    lib_id = lib["id"]

    # Patch conversation to use user's own library -> 200
    res_patch = await client.patch(f"/api/conversations/{conv_id}", json={"library_id": lib_id})
    assert res_patch.status_code == 200
    assert res_patch.json()["library_id"] == lib_id

    # Create other user's library
    async with app.state.services.db.sessionmaker() as session:
        other_user = User(email="victim@ezo.uz", display_name="Victim")
        session.add(other_user)
        await session.flush()
        other_lib = KnowledgeLibrary(user_id=other_user.id, name="Victim Lib", description="")
        session.add(other_lib)
        await session.commit()
        victim_lib_id = str(other_lib.id)

    # Patch conversation with other user's library -> 403 Forbidden
    res_forbidden = await client.patch(
        f"/api/conversations/{conv_id}", json={"library_id": victim_lib_id}
    )
    assert res_forbidden.status_code == 403

    # Clear library via patch (set None) -> 200
    res_clear = await client.patch(f"/api/conversations/{conv_id}", json={"library_id": None})
    assert res_clear.status_code == 200
    assert res_clear.json()["library_id"] is None
