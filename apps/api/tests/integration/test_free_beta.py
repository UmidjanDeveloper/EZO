"""Reduced profile over private object API fixture, never a live cloud."""

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from ezo_api.main import create_app
from ezo_api.storage.supabase import SupabaseStorageProvider
from tests.conftest import make_settings

URL = "https://abcdefghijklmnopqrst.supabase.co"
KEY = "non-secret-storage-transport-fixture-key"


def free_settings(database_url: str, **overrides):
    values = dict(
        EZO_DEPLOYMENT_PROFILE="free-beta",
        EZO_STORAGE_PROVIDER="supabase",
        EZO_SUPABASE_URL=URL,
        EZO_SUPABASE_STORAGE_KEY=KEY,
        EZO_AUTH_MODE="token",
        EZO_API_TOKEN="owner-test-token-32-characters-long",
        EZO_LEARNING_ENABLED=False,
        EZO_RUFLO_ENABLED=False,
        EZO_DEBUG_TRACES=False,
        EZO_WEB_SEARCH_PROVIDER="none",
        EZO_SCHOLAR_PROVIDER="none",
        EZO_VOICE_PROVIDERS="none",
        EZO_IMAGE_PROVIDERS="none",
        EZO_MAX_UPLOAD_MB=4,
        EZO_MAX_MESSAGE_CHARS=4000,
        EZO_RATE_LIMIT_CHAT=5,
        EZO_RATE_LIMIT_CHAT_PER_DAY=10,
        EZO_RATE_LIMIT_DEFAULT=60,
    )
    values.update(overrides)
    return make_settings(database_url, **values)


class CloudFixture:
    """Survives API instances; models Storage REST contract, not cloud guarantees."""

    def __init__(self):
        self.objects = {}
        self.calls = []
        self.public = False
        self.down = False

    def handle(self, request):
        self.calls.append(request)
        assert request.headers["apikey"] == KEY
        assert request.headers["authorization"] == "Bearer " + KEY
        if self.down:
            return httpx.Response(503, text=KEY + " private provider details")
        path = request.url.path.removeprefix("/storage/v1/")
        if path == "bucket/ezo-private":
            return httpx.Response(
                200, json={"id": "ezo-private", "public": self.public, "file_size_limit": 5_000_000}
            )
        if request.method == "DELETE":
            assert path == "object/ezo-private"
            for key in json.loads(request.content)["prefixes"]:
                self.objects.pop(key, None)
            return httpx.Response(200, json=[])
        key = path.removeprefix("object/ezo-private/")
        if request.method == "POST":
            assert request.headers["x-upsert"] == "false"
            if key in self.objects:
                return httpx.Response(409)
            self.objects[key] = request.content
            return httpx.Response(200, json={"Key": key})
        if key not in self.objects:
            return httpx.Response(404)
        return httpx.Response(200, content=self.objects[key] if request.method == "GET" else b"")

    def provider(self):
        return SupabaseStorageProvider(
            URL, KEY, "ezo-private", transport=httpx.MockTransport(self.handle)
        )


@pytest.fixture
async def free_client(database_url):
    cloud = CloudFixture()
    app = create_app(free_settings(database_url), storage=cloud.provider())
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
            headers={"Authorization": "Bearer owner-test-token-32-characters-long"},
        ) as client,
    ):
        yield client, app, cloud


async def test_office_returned_download_is_usable(free_client):
    client, _app, cloud = free_client
    response = await client.post(
        "/api/office/documents",
        json={
            "title": "Owner letter",
            "markdown": "# Salom\n\nPrivate owner content.",
            "export_pdf": False,
        },
    )
    assert response.status_code == 200, response.text
    download = await client.get(response.json()["download_url"])
    assert download.status_code == 200, download.text
    assert download.content.startswith(b"PK")
    assert cloud.objects


async def test_profile_denies_unsupported_before_body_and_preserves_auth(free_client):
    client, _app, _cloud = free_client
    for path in (
        "/api/student/uploads",
        "/api/knowledge/documents",
        "/api/learning/sources",
        "/api/presentations/generate",
        "/api/voice/transcribe",
        "/api/ielts/evaluate",
        "/api/artifacts",
    ):
        response = await client.post(path, content=b"{")
        assert response.status_code == 409, (path, response.text)
        assert (
            await client.post(path, headers={"Authorization": "Bearer wrong"}, content=b"{")
        ).status_code == 401
    assert (await client.get("/api/status")).json()["deployment_profile"] == "free-beta"
    assert (
        await client.post("/api/chat", json={"message": "PDF tayyorla va website o‘rgan"})
    ).json()["agent"] == "general"
    assert (
        await client.post("/api/chat", json={"message": "Hi", "agent": "student"})
    ).status_code == 409
    assert (
        await client.post("/api/personal/consent", json={"consent": True, "auto_memory": True})
    ).status_code == 409
    assert (
        await client.patch("/api/me/preferences", json={"auto_memory": True})
    ).status_code == 409


async def test_small_spreadsheet_export_and_cloud_outage_are_honest(free_client):
    client, _app, cloud = free_client
    body = {
        "title": "Budget",
        "format": "csv",
        "sheets": [{"name": "Sheet", "columns": ["Item"], "rows": [["Private"]]}],
    }
    response = await client.post("/api/office/spreadsheets", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert (await client.get(payload["download_url"])).status_code == 200
    assert (await client.get(payload["exports"]["xlsx"])).status_code == 200
    cloud.down = True
    failed = await client.get(payload["download_url"])
    assert failed.status_code == 503
    assert KEY not in failed.text and "private provider details" not in failed.text
    # An outage is not a missing version, and cannot erase its metadata.
    assert (await client.get("/api/artifacts/" + payload["artifact_id"])).status_code == 200
    assert (
        await client.delete("/api/artifacts/" + payload["artifact_id"] + "?confirm=true")
    ).status_code == 409
    cloud.down = False
    assert (await client.get(payload["download_url"])).status_code == 200


async def test_export_limits_reject_before_cloud_writes(free_client):
    client, _app, cloud = free_client
    count = len(cloud.calls)
    assert (
        await client.post(
            "/api/office/documents",
            json={"title": "Test", "markdown": "x" * 12001, "export_pdf": False},
        )
    ).status_code == 413
    assert (
        await client.post(
            "/api/office/documents", json={"title": "Test", "markdown": "Hello", "export_pdf": True}
        )
    ).status_code == 409
    assert (
        await client.post(
            "/api/office/spreadsheets",
            json={"title": "Test", "sheets": [{"columns": ["a"], "rows": [["x"]] * 201}]},
        )
    ).status_code == 413
    assert len(cloud.calls) == count


async def test_remote_data_survives_api_recreation_and_unauthorized_access(database_url):
    from unittest.mock import patch

    from ezo_api.storage.local import LocalStorageProvider

    cloud = CloudFixture()
    token = {"Authorization": "Bearer owner-test-token-32-characters-long"}
    settings1 = free_settings(database_url)
    settings2 = free_settings(database_url)
    assert settings1.storage_dir != settings2.storage_dir
    with patch.object(LocalStorageProvider, "put", side_effect=AssertionError("local fallback")):
        app = create_app(settings1, storage=cloud.provider())
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url="https://test", headers=token
            ) as c,
        ):
            result = await c.post(
                "/api/office/documents",
                json={
                    "title": "Keep me",
                    "markdown": "# Private\n\nRetained bytes.",
                    "export_pdf": False,
                },
            )
            assert result.status_code == 200
            path = result.json()["download_url"]
            before = (await c.get(path)).content
        second = create_app(settings2, storage=cloud.provider())
        async with (
            second.router.lifespan_context(second),
            AsyncClient(transport=ASGITransport(app=second), base_url="https://test") as c,
        ):
            calls = len(cloud.calls)
            assert (await c.get(path)).status_code == 401
            assert len(cloud.calls) == calls
            response = await c.get(path, headers=token)
            assert response.status_code == 200 and response.content == before
            # Foreign artifact ownership must be checked before storage, not by key secrecy.
            import uuid

            from sqlalchemy import update

            from ezo_api.db.models import Artifact, User

            async with second.state.services.db.sessionmaker() as db:
                foreign = User(email="foreign@example.test", display_name="Foreign", preferences={})
                db.add(foreign)
                await db.flush()
                await db.execute(
                    update(Artifact)
                    .where(Artifact.id == uuid.UUID(result.json()["artifact_id"]))
                    .values(user_id=foreign.id)
                )
                await db.commit()
            calls = len(cloud.calls)
            assert (await c.get(path, headers=token)).status_code == 404
            assert len(cloud.calls) == calls


async def test_free_lifespan_does_not_resume_background_work(database_url):
    from unittest.mock import AsyncMock, patch

    app = create_app(free_settings(database_url), storage=CloudFixture().provider())
    with (
        patch.object(
            app.state.services.ingestion, "resume_unfinished", new_callable=AsyncMock
        ) as ingest,
        patch.object(
            app.state.services.learning, "resume_unfinished", new_callable=AsyncMock
        ) as learn,
    ):
        async with app.router.lifespan_context(app):
            assert app.state.services.tools.names() == []
        ingest.assert_not_awaited()
        learn.assert_not_awaited()


async def test_ielts_free_practice_never_reports_a_synthetic_band(free_client):
    client, _app, _cloud = free_client
    response = await client.post("/api/ielts/sessions", json={})
    assert response.status_code == 200, response.text
    session = response.json()["id"]
    finished = False
    for _ in range(30):
        result = await client.post(
            f"/api/ielts/sessions/{session}/advance",
            json={"answer": "I enjoy reading and learning new skills."},
        )
        assert result.status_code == 200, result.text
        if result.json()["finished"]:
            assert result.json()["estimated_band_low"] is None
            assert result.json()["estimated_band_high"] is None
            assert "No AI" in result.json()["feedback"]
            finished = True
            break
    assert finished


async def test_manual_core_data_and_explicit_offline_chat(free_client):
    client, _app, _cloud = free_client
    assert (await client.post("/api/projects", json={"name": "Private study"})).status_code == 201
    memory = await client.post("/api/memories", json={"content": "I study Uzbek books."})
    assert memory.status_code == 201, memory.text
    assert (
        await client.patch(
            "/api/memories/" + memory.json()["id"], json={"content": "I study Uzbek and English."}
        )
    ).status_code == 200
    assert (
        await client.post("/api/personal/goals", json={"title": "Read regularly"})
    ).status_code == 201
    assert (await client.get("/api/personal/goals")).json()[0]["title"] == "Read regularly"
    assert (await client.get("/api/memories/export")).status_code == 200
    response = await client.post("/api/chat", json={"message": "Hello"})
    assert response.status_code == 200
    assert response.json()["message"]["metadata"]["provider"] == "offline"
    assert "not an AI answer" in response.json()["message"]["content"]


async def test_storage_policy_startup_guard_requires_rls_and_rejects_public_policies(database_url):
    if not database_url.startswith("postgres"):
        pytest.skip("real PostgreSQL storage policy catalog required")
    from sqlalchemy import create_engine, text

    from ezo_api.db.session import to_sync_url
    from ezo_api.deployment import DeploymentError, check_database, check_database_role

    engine = create_engine(to_sync_url(database_url))
    settings = free_settings(
        database_url, EZO_ENV="production", EZO_CORS_ORIGINS="https://owner.example.test"
    )
    try:
        with engine.begin() as db:
            db.execute(text("CREATE SCHEMA storage"))
            db.execute(
                text(
                    "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles "
                    "WHERE rolname='ezo_profile_guard') THEN "
                    "CREATE ROLE ezo_profile_guard NOLOGIN; END IF; END $$"
                )
            )
            db.execute(text("GRANT USAGE ON SCHEMA public TO ezo_profile_guard"))
            db.execute(text("CREATE TABLE storage.objects(id int)"))
            db.execute(text("CREATE TABLE storage.buckets(id int)"))
        with pytest.raises(DeploymentError, match="non-privileged"):
            check_database_role(settings)
        with pytest.raises(DeploymentError, match="non-privileged"):
            check_database(settings)
        settings = settings.model_copy(
            update={"database_url": database_url + "?options=-crole%3Dezo_profile_guard"}
        )
        check_database_role(settings)
        with pytest.raises(DeploymentError, match="Storage requires RLS"):
            check_database(settings)
        with engine.begin() as db:
            db.execute(text("ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY"))
            db.execute(text("ALTER TABLE storage.buckets ENABLE ROW LEVEL SECURITY"))
        check_database(settings)
        with engine.begin() as db:
            db.execute(
                text(
                    "DO $$ BEGIN EXECUTE format('GRANT %I TO ezo_profile_guard', "
                    "current_user); END $$"
                )
            )
        try:
            with pytest.raises(DeploymentError, match="non-privileged"):
                check_database_role(settings)
        finally:
            with engine.begin() as db:
                db.execute(
                    text(
                        "DO $$ BEGIN EXECUTE format('REVOKE %I FROM ezo_profile_guard', "
                        "current_user); END $$"
                    )
                )
        with engine.begin() as db:
            db.execute(
                text(
                    "CREATE POLICY accidental_public_read ON storage.objects "
                    "FOR SELECT TO PUBLIC USING (true)"
                )
            )
        with pytest.raises(DeploymentError, match="Storage requires RLS"):
            check_database(settings)
    finally:
        with engine.begin() as db:
            db.execute(text("DROP SCHEMA IF EXISTS storage CASCADE"))
        engine.dispose()


async def test_direct_office_and_ielts_cannot_link_another_owners_conversation(free_client):
    from ezo_api.db.models import Conversation, User

    client, app, cloud = free_client
    async with app.state.services.db.sessionmaker() as db:
        other = User(email="other-scope@example.test", display_name="Other", preferences={})
        db.add(other)
        await db.flush()
        conversation = Conversation(user_id=other.id, title="Private foreign conversation")
        db.add(conversation)
        await db.commit()
        foreign = str(conversation.id)
    calls = len(cloud.calls)
    for path, body in (
        ("/api/office/documents", {"title": "Test", "markdown": "Hello", "export_pdf": False}),
        (
            "/api/office/spreadsheets",
            {"title": "Test", "sheets": [{"columns": ["A"], "rows": [["B"]]}]},
        ),
        ("/api/ielts/sessions", {}),
    ):
        response = await client.post(path, json={**body, "conversation_id": foreign})
        assert response.status_code == 404, response.text
    assert len(cloud.calls) == calls
