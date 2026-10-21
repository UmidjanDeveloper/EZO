"""Public health semantics and owner access across the deployed HTTP boundary."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from ezo_api.main import create_app
from tests.conftest import make_settings
from tests.unit.test_deployment import production


async def test_unhealthy_database_is_a_failing_probe(client: AsyncClient) -> None:
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", AsyncMock(side_effect=OSError)):
        response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


async def test_owner_token_protects_chat_and_files(database_url: str) -> None:
    token = "owner-access-integration-test-token"
    app = create_app(make_settings(database_url, EZO_AUTH_MODE="token", EZO_API_TOKEN=token))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/health")).status_code == 200
            for headers in ({}, {"Authorization": "Bearer wrong-token"}):
                assert (await client.get("/api/artifacts", headers=headers)).status_code == 401
                assert (
                    await client.post(
                        "/api/chat",
                        json={"message": "Salom"},
                        headers=headers,
                    )
                ).status_code == 401
            headers = {"Authorization": f"Bearer {token}"}
            assert (await client.get("/api/me", headers=headers)).status_code == 200
            response = await client.post("/api/chat", json={"message": "Salom"}, headers=headers)
            assert response.status_code == 200
            assert response.json()["message"]["metadata"]["provider"] == "offline"
    finally:
        await app.state.services.db.dispose()


async def test_production_cors_and_hidden_docs() -> None:
    # App construction creates no connection to this deliberately non-routable test DSN.
    app = create_app(production(EZO_OCR_PROVIDER="none", EZO_OFFICE_CONVERTER="none"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/docs", "/redoc", "/openapi.json"):
                assert (await client.get(path)).status_code == 404
            for origin, expected in (("https://ezo.example.com", 200), ("https://evil.test", 400)):
                response = await client.options(
                    "/api/chat",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "authorization,content-type",
                    },
                )
                assert response.status_code == expected
                if expected == 200:
                    assert response.headers["access-control-allow-origin"] == origin
    finally:
        await app.state.services.db.dispose()


async def test_attackers_cannot_use_up_the_owner_limits_or_the_health_probe(
    database_url: str,
) -> None:
    token = "owner-access-integration-test-token"
    app = create_app(
        make_settings(
            database_url,
            EZO_AUTH_MODE="token",
            EZO_API_TOKEN=token + "\n",  # a copied secret with a newline still works
            EZO_RATE_LIMIT_CHAT="2",
            EZO_RATE_LIMIT_DEFAULT="3",
            EZO_RATE_LIMIT_CHAT_PER_DAY="3",
            EZO_MAX_UPLOAD_MB="1",
        )
    )
    owner = {"Authorization": f"Bearer {token}"}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(6):  # the probe is never rate limited
                assert (await client.get("/api/health")).status_code == 200
            for _ in range(5):  # unauthenticated traffic does not count against the owner
                assert (await client.post("/api/chat", json={"message": "x"})).status_code == 401
            for _ in range(2):
                response = await client.post("/api/chat", json={"message": "Salom"}, headers=owner)
                assert response.status_code == 200
            limited = await client.post("/api/chat", json={"message": "Salom"}, headers=owner)
            assert limited.status_code == 429 and limited.headers["retry-after"]
            # An oversized upload is refused at the edge, also for the owner.
            big = b"x" * (4 * 1024 * 1024)
            too_large = await client.post(
                "/api/knowledge/documents", files={"file": ("big.txt", big)}, headers=owner
            )
            assert too_large.status_code == 413
            assert too_large.json()["error"]["code"] == "too_large"
    finally:
        await app.state.services.db.dispose()


async def test_daily_ai_budget(database_url: str) -> None:
    app = create_app(make_settings(database_url, EZO_RATE_LIMIT_CHAT_PER_DAY="1"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/api/chat", json={"message": "a"})).status_code == 200
            assert (await client.post("/api/chat", json={"message": "b"})).status_code == 429
    finally:
        await app.state.services.db.dispose()


async def test_public_health_hides_the_version_in_production() -> None:
    app = create_app(production(EZO_OCR_PROVIDER="none", EZO_OFFICE_CONVERTER="none"))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", AsyncMock()):
                response = await client.get("/api/health")
        assert response.status_code == 200 and "version" not in response.json()
    finally:
        await app.state.services.db.dispose()


async def test_merged_workspaces_require_token_with_production_policy() -> None:
    """No database/provider or request validation may precede owner authentication."""
    app = create_app(
        production(
            OPENAI_API_KEY="",
            ANTHROPIC_API_KEY="",
            GEMINI_API_KEY="",
            EZO_OCR_PROVIDER="none",
            EZO_OFFICE_CONVERTER="none",
        )
    )
    try:
        assert app.state.services.router.is_offline
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            for method, path in (
                ("GET", "/api/personal/profile"),
                ("GET", "/api/personal/memories/export"),
                ("POST", "/api/personal/consent"),
                ("POST", "/api/personal/goals"),
                ("GET", "/api/student/status"),
                ("POST", "/api/student/readings"),
                ("POST", "/api/ielts/sessions"),
                ("POST", "/api/ielts/evaluate"),
                ("POST", "/api/presentations/generate"),
                ("POST", "/api/office/documents"),
                ("POST", "/api/office/spreadsheets"),
            ):
                for headers in ({}, {"Authorization": "Bearer invalid"}):
                    response = await client.request(method, path, headers=headers, content=b"{")
                    assert response.status_code == 401, (method, path, response.text)
    finally:
        await app.state.services.db.dispose()
