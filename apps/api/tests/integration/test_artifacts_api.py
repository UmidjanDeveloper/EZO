from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from ezo_api.artifacts.service import ArtifactError
from ezo_api.db.models import Artifact, Message, User
from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat


async def create_text(client: AsyncClient, **body: object) -> dict:  # type: ignore[type-arg]
    payload = {"title": "Reja", "content": "# Reja\n\n1. Birinchi qadam", **body}
    response = await client.post("/api/artifacts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_create_download_and_details(client: AsyncClient) -> None:
    artifact = await create_text(client)
    assert artifact["type"] == "document" and artifact["status"] == "ready"
    assert artifact["version_count"] == 1
    current = artifact["current_version"]
    assert current["version_number"] == 1 and current["filename"] == "Reja.md"
    assert current["mime_type"].startswith("text/markdown") and current["is_text"] is True

    download = await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")
    assert download.status_code == 200
    assert download.content == b"# Reja\n\n1. Birinchi qadam"
    assert download.headers["content-disposition"].startswith('attachment; filename="Reja.md"')
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-security-policy"] == "sandbox"


async def test_edits_create_new_versions_and_keep_old_ones(client: AsyncClient) -> None:
    artifact = await create_text(client)
    url = f"/api/artifacts/{artifact['id']}"
    edited = (
        await client.post(
            f"{url}/versions", json={"content": "# Reja v2", "change_summary": "Qisqartirildi"}
        )
    ).json()
    assert [v["version_number"] for v in edited["versions"]] == [2, 1]
    assert (
        edited["versions"][0]["current"]
        and edited["versions"][0]["change_summary"] == "Qisqartirildi"
    )
    assert edited["versions"][0]["parent_version_id"] == edited["versions"][1]["id"]

    # identical content is not a new version
    same = (await client.post(f"{url}/versions", json={"content": "# Reja v2"})).json()
    assert len(same["versions"]) == 2

    # the old version is untouched
    old = (await client.get(f"{url}/versions/1/text")).json()
    assert old["text"].startswith("# Reja\n")
    assert (await client.get(f"{url}/versions/2/text")).json()["text"] == "# Reja v2"


async def test_restore_adds_a_version_instead_of_rewriting_history(client: AsyncClient) -> None:
    artifact = await create_text(client)
    url = f"/api/artifacts/{artifact['id']}"
    await client.post(f"{url}/versions", json={"content": "noto'g'ri tahrir"})
    restored = (await client.post(f"{url}/versions/1/restore")).json()
    versions = restored["versions"]
    assert [v["version_number"] for v in versions] == [3, 2, 1]
    assert versions[0]["current"] and versions[0]["created_by"] == "restore"
    assert versions[0]["change_summary"] == "Restored from version 1"
    assert versions[0]["parent_version_id"] == versions[2]["id"]
    assert versions[0]["content_hash"] == versions[2]["content_hash"]
    assert (await client.get(f"{url}/versions/2/text")).json()["text"] == "noto'g'ri tahrir"
    # restoring the current version again changes nothing
    assert len((await client.post(f"{url}/versions/3/restore")).json()["versions"]) == 3
    assert (await client.post(f"{url}/versions/9/restore")).status_code == 404


async def test_rename_list_filters_and_delete(client: AsyncClient, app: FastAPI) -> None:
    project = (await client.post("/api/projects", json={"name": "Loyiha"})).json()
    doc = await create_text(client, project_id=project["id"])
    await create_text(client, title="Jadval", type="spreadsheet", format="csv", content="a,b\n1,2")

    renamed = (
        await client.patch(f"/api/artifacts/{doc['id']}", json={"title": "  Yangi   nom "})
    ).json()
    assert renamed["title"] == "Yangi nom"
    assert renamed["current_version"]["version_number"] == 1  # renaming is not a content change

    assert len((await client.get("/api/artifacts")).json()) == 2
    assert [
        a["title"]
        for a in (await client.get("/api/artifacts", params={"type": "spreadsheet"})).json()
    ] == ["Jadval"]
    assert [
        a["id"]
        for a in (await client.get("/api/artifacts", params={"project_id": project["id"]})).json()
    ] == [doc["id"]]

    storage = Path(app.state.services.settings.storage_dir)
    assert any(storage.rglob("*.md"))  # noqa: ASYNC240
    assert (await client.delete(f"/api/artifacts/{doc['id']}")).status_code == 400  # needs confirm
    assert (
        await client.delete(f"/api/artifacts/{doc['id']}", params={"confirm": "true"})
    ).status_code == 204
    assert (await client.get(f"/api/artifacts/{doc['id']}")).status_code == 404
    assert not any(storage.rglob("*.md"))  # noqa: ASYNC240


async def test_deleting_a_project_keeps_its_artifacts(client: AsyncClient) -> None:
    project = (await client.post("/api/projects", json={"name": "Vaqtinchalik"})).json()
    doc = await create_text(client, project_id=project["id"])
    assert (await client.delete(f"/api/projects/{project['id']}")).status_code == 204
    kept = (await client.get(f"/api/artifacts/{doc['id']}")).json()
    assert kept["project_id"] is None and kept["version_count"] == 1


async def test_other_users_artifacts_are_invisible(client: AsyncClient, app: FastAPI) -> None:
    services = app.state.services
    async with services.db.sessionmaker() as session:
        stranger = User(email="other@x", display_name="Other", preferences={})
        session.add(stranger)
        await session.flush()
        result = await services.artifacts.create(
            session,
            stranger.id,
            title="Maxfiy",
            artifact_type="document",
            filename="maxfiy.md",
            data=b"secret",
        )
        await session.commit()
        foreign = result.artifact.id
    assert (await client.get("/api/artifacts")).json() == []
    for method, path in [
        ("GET", f"/api/artifacts/{foreign}"),
        ("GET", f"/api/artifacts/{foreign}/versions/1/download"),
        ("GET", f"/api/artifacts/{foreign}/versions/1/text"),
        ("PATCH", f"/api/artifacts/{foreign}"),
        ("POST", f"/api/artifacts/{foreign}/versions/1/restore"),
        ("DELETE", f"/api/artifacts/{foreign}?confirm=true"),
    ]:
        response = await client.request(
            method, path, json={"title": "x"} if method == "PATCH" else None
        )
        assert response.status_code == 404, (method, path, response.status_code)


async def test_save_answer_from_conversation(
    client: AsyncClient, app: FastAPI, fake_anthropic: FakeProvider
) -> None:
    events = await stream_chat(client, message="Menga qisqa reja yozib ber")
    done = events[-1][1]["message"]
    saved = await create_text(client, title="Javob", content=done["content"], message_id=done["id"])
    assert saved["conversation_id"] == done["conversation_id"]
    assert saved["metadata"]["saved_from_message"] == done["id"]

    messages = (await client.get(f"/api/conversations/{done['conversation_id']}/messages")).json()
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert assistant["metadata"]["artifacts"] == [
        {"id": saved["id"], "title": "Javob", "type": "document", "version": 1}
    ]

    by_conversation = (
        await client.get("/api/artifacts", params={"conversation_id": done["conversation_id"]})
    ).json()
    assert [a["id"] for a in by_conversation] == [saved["id"]]


async def test_rejects_unknown_message_and_non_text_edit(client: AsyncClient, app: FastAPI) -> None:
    import uuid

    missing = await client.post(
        "/api/artifacts", json={"title": "x", "content": "y", "message_id": str(uuid.uuid4())}
    )
    assert missing.status_code == 404

    services = app.state.services
    async with services.db.sessionmaker() as session:
        owner = await session.scalar(select(User))
        if owner is None:
            await client.get("/api/me")
            owner = await session.scalar(select(User))
        assert owner is not None
        image = await services.artifacts.create(
            session,
            owner.id,
            title="Rasm",
            artifact_type="image",
            filename="rasm.png",
            data=b"\x89PNG\r\n\x1a\nxx",
        )
        await session.commit()
        image_id = image.artifact.id
    edit = await client.post(f"/api/artifacts/{image_id}/versions", json={"content": "text"})
    assert edit.status_code == 409
    assert (await client.get(f"/api/artifacts/{image_id}/versions/1/text")).status_code == 409


async def test_service_rejects_unsafe_types(app: FastAPI) -> None:
    services = app.state.services
    async with services.db.sessionmaker() as session:
        user = User(email="u@x", display_name="U", preferences={})
        session.add(user)
        await session.flush()
        with pytest.raises(ArtifactError) as caught:
            await services.artifacts.create(
                session,
                user.id,
                title="x",
                artifact_type="document",
                filename="virus.exe",
                data=b"MZ",
            )
        assert caught.value.code == "unsupported_type"
        with pytest.raises(ArtifactError):
            await services.artifacts.create(
                session, user.id, title="x", artifact_type="nope", filename="a.md", data=b"a"
            )
        with pytest.raises(ArtifactError):
            await services.artifacts.create(
                session, user.id, title="x", artifact_type="document", filename="a.md", data=b""
            )
        # path tricks in names never reach storage keys
        result = await services.artifacts.create(
            session,
            user.id,
            title="x",
            artifact_type="document",
            filename="../../etc/passwd.md",
            data=b"a",
        )
        assert result.version.filename == "passwd.md"
        assert result.version.storage_key.startswith(f"artifacts/{user.id}/")
        assert (
            await session.scalar(select(Artifact).where(Artifact.id == result.artifact.id))
            is not None
        )
        assert await session.scalar(select(Message)) is None


async def test_cors_exposes_download_filename(client: AsyncClient) -> None:
    artifact = await create_text(client)
    origin = {"Origin": "http://localhost:3000"}
    download = await client.get(
        f"/api/artifacts/{artifact['id']}/versions/1/download", headers=origin
    )
    exposed = download.headers["access-control-expose-headers"]
    assert "Content-Disposition" in exposed
    preflight = await client.options(
        f"/api/stories/{artifact['id']}/scenes",
        headers={**origin, "Access-Control-Request-Method": "PUT"},
    )
    assert (
        preflight.status_code == 200 and "PUT" in preflight.headers["access-control-allow-methods"]
    )
