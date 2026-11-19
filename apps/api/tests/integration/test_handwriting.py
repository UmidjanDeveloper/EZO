"""Handwriting goes to the vision model; the transcription comes back as text and Word."""

from __future__ import annotations

import io

from docx import Document
from httpx import AsyncClient

from tests.fakes import FakeProvider, png_bytes
from tests.integration.helpers import stream_chat


async def test_handwritten_page_becomes_text_and_word(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    upload = await client.post(
        "/api/knowledge/documents", files={"file": ("ariza.png", png_bytes(400, 300), "image/png")}
    )
    assert upload.status_code in (200, 201), upload.text
    document = upload.json()["document"]
    fake_anthropic.replies = [
        "Hokimga\nAliyev Botirdan\nAriza\nMenga [?] yordam berishingizni so'rayman.",
        "Mana matn.",
    ]
    events = await stream_chat(
        client, message="Shu qo'lyozmani matnga aylantir", attachments=[document["id"]]
    )
    vision = fake_anthropic.requests[0]
    asked = vision.messages[-1]
    assert asked.images and "Transcribe the handwritten text" in asked.content
    system = fake_anthropic.requests[-1].system or ""
    assert "1 word(s) marked [?]" in system and "Aliyev Botirdan" in system
    [artifact] = events[-1][1]["message"]["metadata"]["artifacts"]
    data = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).content
    text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    assert "Aliyev Botirdan" in text and "[?]" in text
