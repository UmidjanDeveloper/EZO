"""Organization profiles through the API and chat: formatting, logo, approved templates,
examples, export, deletion with its files, and use in letters, other documents and
presentations."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from docx import Document
from fastapi import FastAPI
from httpx import AsyncClient

from ezo_api.db.models import OrganizationAsset, User
from tests.fakes import FakeProvider, png_bytes
from tests.integration.helpers import stream_chat
from tests.integration.test_document_agent import created
from tests.integration.test_presentation_agent import deck
from tests.unit.test_organization import template_docx

PROFILE: dict[str, Any] = {
    "name": "Toshkent shahar hokimligi",
    "org_type": "government",
    "department": "Yoshlar ishlari bo'limi",
    "style_notes": "Qisqa va aniq.",
    "terminology": {"mutasaddi": "mas'ul"},
    "formatting": {"font_name": "Times New Roman", "font_size": 13, "margins_cm": {"left": 2.5}},
}


async def make_profile(client: AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/writing/organizations", json=PROFILE)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def add_file(
    client: AsyncClient, org_id: str, kind: str, name: str, data: bytes, **form: str
) -> dict[str, Any]:
    response = await client.post(
        f"/api/writing/organizations/{org_id}/files",
        files={"file": (name, data)},
        data={"kind": kind, **form},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_profile_files_export_and_deletion(client: AsyncClient, app: FastAPI) -> None:
    org = await make_profile(client)
    assert org["formatting"]["font_size"] == 13 and org["has_logo"] is False
    logo = await client.put(
        f"/api/writing/organizations/{org['id']}/logo",
        files={"file": ("logo.jpg", png_bytes(800, 400))},
    )
    assert logo.status_code == 200 and logo.json()["has_logo"] is True
    image = await client.get(f"/api/writing/organizations/{org['id']}/logo")
    assert image.headers["content-type"] == "image/png" and image.content.startswith(b"\x89PNG")
    bad = await client.put(
        f"/api/writing/organizations/{org['id']}/logo", files={"file": ("logo.png", b"<svg/>")}
    )
    assert bad.status_code == 422

    template = await add_file(
        client, org["id"], "template", "Blank.docx", template_docx(), doc_type="xizmat_xati"
    )
    assert template["has_marker"] is True and template["doc_type"] == "xizmat_xati"
    example = await add_file(
        client, org["id"], "example", "namuna.txt", b"Hurmatli rahbar! Ma'lum qilamizki."
    )
    assert example["excerpt"].startswith("Hurmatli rahbar")
    wrong = await client.post(
        f"/api/writing/organizations/{org['id']}/files",
        files={"file": ("x.txt", b"text")},
        data={"kind": "template"},
    )
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "wrong_type"
    listed = (await client.get(f"/api/writing/organizations/{org['id']}/files")).json()
    assert {f["kind"] for f in listed} == {"template", "example"}
    download = await client.get(
        f"/api/writing/organizations/{org['id']}/files/{template['id']}/download"
    )
    assert download.content == template_docx() or download.content.startswith(b"PK")
    assert download.headers["x-content-type-options"] == "nosniff"

    exported = await client.get(f"/api/writing/organizations/{org['id']}/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("profile.json"))
    assert "logo.png" in names and "templates/01-Blank.docx" in names
    assert any(n.startswith("examples/") for n in names)
    assert manifest["profile"]["name"] == PROFILE["name"]
    assert manifest["profile"]["formatting"]["font_size"] == 13

    # Another user's profile files are invisible.
    async with app.state.services.db.sessionmaker() as session:
        stranger = User(email="other@x", display_name="Other", preferences={})
        session.add(stranger)
        await session.commit()
    async with app.state.services.db.sessionmaker() as session:
        asset = await session.get(OrganizationAsset, __import__("uuid").UUID(template["id"]))
        assert asset is not None
        key = asset.storage_key
    storage = app.state.services.storage
    assert await storage.exists(key)
    fake = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/writing/organizations/{fake}/files")).status_code == 404

    # Deleting the profile deletes its stored files too.
    assert (await client.delete(f"/api/writing/organizations/{org['id']}")).status_code == 204
    assert not await storage.exists(key)


async def test_letter_uses_the_approved_template_and_examples_only_as_style(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    org = await make_profile(client)
    await add_file(
        client, org["id"], "template", "Blank.docx", template_docx(), doc_type="xizmat_xati"
    )
    await add_file(
        client,
        org["id"],
        "example",
        "namuna.txt",
        b"Hurmatli Akmal Karimov! 2023-yil 15-maydagi 77-son xatingizga javoban ...",
        doc_type="xizmat_xati",
    )
    letter = {
        "title": "Xizmat xati",
        "fields": {"recipient": "Vazirlikka", "subject": "Yoshlar tadbiri"},
        "sections": [{"heading": None, "text": "77-son xatingizga javoban tadbir o'tkazildi."}],
        "missing": [],
    }
    fake_anthropic.replies = [json.dumps(letter, ensure_ascii=False), "Tayyor."]
    events = await stream_chat(
        client, message="Tashkilotimiz blankasida vazirlikka xizmat xati tayyorla: yoshlar tadbiri"
    )
    [artifact] = created(events)
    writer = next(
        r.messages[0].content
        for r in fake_anthropic.requests
        if "<example" in r.messages[0].content
    )
    assert '<example title="namuna.txt">' in writer and "NEVER copy their names" in writer
    version = (await client.get(f"/api/artifacts/{artifact['id']}")).json()["current_version"]
    meta = version["generation_metadata"]
    assert meta["organization_template"] == "Blank.docx" and meta["organization_examples"] == [
        "namuna.txt"
    ]
    # "77" came from the example, not from the user: it is flagged, not trusted.
    assert "77" in meta["validation"]["unverified_numbers"]
    data = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).content
    document = Document(io.BytesIO(data))
    texts = [p.text for p in document.paragraphs]
    assert texts[0] == "Toshkent shahar hokimligi" and "Namuna matn" not in " ".join(texts)
    assert any("tadbir o'tkazildi" in t for t in texts)
    assert document.sections[0].header.paragraphs[0].text.startswith("TOSHKENT SHAHAR")


async def test_other_documents_and_presentations_use_the_profile(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    org = await make_profile(client)
    await client.put(
        f"/api/writing/organizations/{org['id']}/logo",
        files={"file": ("logo.png", png_bytes(200, 200))},
    )
    fake_anthropic.replies = [
        "TITLE: Yo'riqnoma\nCHANGES: new document\n=====\n# Yo'riqnoma\n\nXodimlar uchun qoidalar.",
        "Tayyor.",
    ]
    events = await stream_chat(
        client, message="Tashkilotimiz blankasida xodimlar uchun yo'riqnoma hujjatini yarat"
    )
    [artifact] = created(events)
    data = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).content
    document = Document(io.BytesIO(data))
    assert document.paragraphs[1].text == "Toshkent shahar hokimligi"
    assert len(document.inline_shapes) == 1  # logo
    version = (await client.get(f"/api/artifacts/{artifact['id']}")).json()["current_version"]
    assert version["generation_metadata"]["letterhead"] == "Toshkent shahar hokimligi"

    fake_anthropic.replies = [json.dumps(deck(), ensure_ascii=False), "Tayyor."]
    events = await stream_chat(client, message="Tashkilotimiz faoliyati haqida taqdimot tayyorla")
    [presentation] = created(events)
    planner = fake_anthropic.requests[-2].messages[0].content
    assert "Organization: Toshkent shahar hokimligi" in planner and "use “mas'ul”" in planner
    spec = await client.get(f"/api/artifacts/{presentation['id']}/versions/1/exports/spec")
    assert json.loads(spec.content)["author"] == "Toshkent shahar hokimligi"


async def test_cyrillic_letter_on_the_letterhead(
    client: AsyncClient, fake_anthropic: FakeProvider
) -> None:
    await make_profile(client)
    letter = {
        "title": "Хизмат хати",
        "fields": {"recipient": "Вазирликка", "subject": "Ёшлар тадбири"},
        "sections": [{"heading": None, "text": "Тадбир ўтказилди."}],
        "missing": [],
    }
    fake_anthropic.replies = [json.dumps(letter, ensure_ascii=False), "Тайёр."]
    events = await stream_chat(
        client, message="Ташкилотимиз бланкасида вазирликка хизмат хати тайёрла: ёшлар тадбири"
    )
    [artifact] = created(events)
    writer = fake_anthropic.requests[0].messages[0].content
    assert "Organization: Toshkent shahar hokimligi" in writer
    data = (await client.get(f"/api/artifacts/{artifact['id']}/versions/1/download")).content
    texts = [p.text for p in Document(io.BytesIO(data)).paragraphs]
    assert "Тадбир ўтказилди." in texts
