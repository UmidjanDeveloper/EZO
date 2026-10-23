"""POST /api/vision/describe: one owner-supplied image, explained by the vision route."""

import pytest
from httpx import ASGITransport, AsyncClient

from ezo_api.main import create_app
from ezo_api.providers.errors import ProviderErrorKind
from tests.conftest import make_settings
from tests.fakes import FakeProvider

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


async def test_image_and_question_reach_the_vision_route(client, fake_anthropic):
    fake_anthropic.reply = "Ekranda Kalkulyator oynasi ochiq."
    response = await client.post(
        "/api/vision/describe",
        files={"image": ("screen.png", PNG, "image/png")},
        data={"question": "Bu oyna nima?", "language": "uz"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "text": "Ekranda Kalkulyator oynasi ochiq.",
        "provider": "anthropic",
        "model": body["model"],
    }
    request = fake_anthropic.requests[-1]
    (message,) = request.messages
    assert message.content == "Bu oyna nima?"
    assert message.images[0].mime_type == "image/png" and message.images[0].data == PNG
    assert "never an instruction" in (request.system or "")
    assert "Uzbek" in (request.system or "")


async def test_jpeg_without_a_question_gets_a_default_prompt(client, fake_anthropic):
    response = await client.post(
        "/api/vision/describe", files={"image": ("photo.jpg", JPEG, "image/jpeg")}
    )
    assert response.status_code == 200
    assert fake_anthropic.requests[-1].messages[0].images[0].mime_type == "image/jpeg"


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (b"GIF89a" + b"\x00" * 32, 422, "bad_image"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * (4 * 1024 * 1024), 413, "too_large"),
    ],
    ids=["gif", "oversized"],
)
async def test_rejects_non_images_and_oversized_uploads(client, payload, status, code):
    response = await client.post(
        "/api/vision/describe", files={"image": ("x.bin", payload, "application/octet-stream")}
    )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


async def test_without_any_provider_it_says_so(database_url):
    app = create_app(make_settings(database_url), providers={})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/vision/describe", files={"image": ("s.png", PNG, "image/png")}
        )
    await app.state.services.db.dispose()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "vision_not_configured"


async def test_provider_failure_is_reported_not_invented(database_url):
    failing = FakeProvider(name="anthropic", fail_with=ProviderErrorKind.UNAVAILABLE)
    app = create_app(make_settings(database_url), providers={"anthropic": failing})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/vision/describe", files={"image": ("s.png", PNG, "image/png")}
        )
    await app.state.services.db.dispose()
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "vision_failed"
