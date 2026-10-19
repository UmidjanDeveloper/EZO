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
