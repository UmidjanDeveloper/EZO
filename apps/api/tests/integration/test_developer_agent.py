"""Developer Agent through the chat API: build a website, change it, and fail honestly."""

from __future__ import annotations

import io
import zipfile

from httpx import AsyncClient

from tests.fakes import FakeProvider
from tests.integration.helpers import stream_chat

SITE = """<<<FILE index.html>>>
<!doctype html><html><head><link rel="stylesheet" href="style.css"></head>
<body><h1>Oqtepa Kafe</h1><button class="btn">Buyurtma</button>
<script src="script.js"></script></body></html>
<<<END>>>
<<<FILE style.css>>>
.btn { background: red; }
<<<END>>>
<<<FILE script.js>>>
document.querySelector(".btn").onclick = () => alert("Rahmat!");
<<<END>>>
<<<FILE README.md>>>
# Oqtepa Kafe sayti

index.html faylini ikki marta bosing.
<<<END>>>
"""


async def zip_files(client: AsyncClient, artifact_id: str, version: int) -> dict[str, str]:
    response = await client.get(f"/api/artifacts/{artifact_id}/versions/{version}/download")
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {name.split("/", 1)[1]: archive.read(name).decode() for name in archive.namelist()}


async def test_build_a_website_then_change_it(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.replies = [SITE, "Sayt tayyor! index.html ni oching."]
    events = await stream_chat(client, message="Menga kafe uchun website tuzib ber")
    meta = events[0][1]
    assert meta["agent"] == "developer" and meta["requested_agent_available"] is True
    build_request = fake_anthropic.requests[-2]
    assert "Build this: Menga kafe uchun website tuzib ber" in build_request.messages[0].content
    assert "<<<FILE relative/path.ext>>>" in (build_request.system or "")
    system = fake_anthropic.requests[-1].system or ""
    assert "EZO built the project “Oqtepa Kafe sayti”: 4 files" in system
    assert "EZO did NOT run or test the code" in system

    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    assert artifact["type"] == "code" and artifact["version"] == 1
    files = await zip_files(client, artifact["id"], 1)
    assert set(files) == {"index.html", "style.css", "script.js", "README.md"}

    site = await client.get(f"/api/artifacts/{artifact['id']}/versions/1/exports/site")
    assert site.status_code == 200
    assert "<style>\n.btn { background: red; }" in site.text and "alert(" in site.text

    # A follow-up in ordinary words changes the same project (a new version).
    fake_anthropic.replies = [
        "<<<FILE style.css>>>\n.btn { background: blue; }\n<<<END>>>\n",
        "Tugma endi ko'k.",
    ]
    conversation_id = meta["conversation_id"]
    events = await stream_chat(
        client, message="Tugmani ko'k rangga o'zgartir", conversation_id=conversation_id
    )
    assert events[0][1]["agent"] == "developer"
    edit_request = fake_anthropic.requests[-2]
    assert "The current project files:" in edit_request.messages[0].content
    assert ".btn { background: red; }" in edit_request.messages[0].content
    assert "CHANGING an existing project" in (edit_request.system or "")
    [changed] = events[-1][1]["message"]["metadata"]["artifacts"]
    assert changed["id"] == artifact["id"] and changed["version"] == 2
    files = await zip_files(client, artifact["id"], 2)
    assert files["style.css"] == ".btn { background: blue; }\n"
    assert "index.html" in files and "README.md" in files


async def test_a_reply_without_files_is_reported_not_faked(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.replies = ["I'm sorry, I can't do that.", "Loyiha tayyor!"]
    events = await stream_chat(client, message="Python'da kalkulyator dasturi yozib ber")
    assert events[0][1]["agent"] == "developer"
    message = events[-1][1]["message"]
    assert not message["metadata"].get("artifacts")
    # EZO's fixed notice, not the model's "Loyiha tayyor!", says no file was made.
    assert "Fayl yaratilmadi" in message["content"]


async def test_a_code_question_is_answered_without_building(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    fake_anthropic.reply = "Bu funksiya ro'yxatni saralaydi."
    events = await stream_chat(client, message="Bu python kod nima qiladi: sorted(x)")
    assert events[0][1]["agent"] == "developer"
    assert len(fake_anthropic.requests) == 1  # no build call
    assert not events[-1][1]["message"]["metadata"].get("artifacts")
