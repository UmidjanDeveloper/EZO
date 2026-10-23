"""Integration tests for Presentation Maker 2.0 and Office Workspace."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_presentation_themes_and_intake(client: AsyncClient) -> None:
    # 1. List themes
    themes_resp = await client.get("/api/presentations/themes")
    assert themes_resp.status_code == 200
    themes = themes_resp.json()
    assert any(t["name"] == "ezo" for t in themes)
    assert any(t["name"] == "midnight" for t in themes)

    # 2. Intake brief
    brief = {
        "title": "Sun'iy Intellekt va Kelajak",
        "topic": (
            "O'zbekistonda ta'lim tizimini sun'iy intellekt orqali rivojlantirish istiqbollari"
        ),
        "audience": "O'qituvchilar va talabalar",
        "slide_count": 5,
        "theme": "ezo",
        "language": "uz",
        "key_points": ["Adaptiv ta'lim", "Avtomatlashtirilgan baholash"],
    }
    intake_resp = await client.post("/api/presentations/intake", json=brief)
    assert intake_resp.status_code == 200
    outline = intake_resp.json()
    assert outline["title"] == brief["title"]
    assert outline["slide_count"] == 5
    assert len(outline["slides"]) == 5
    assert outline["slides"][0]["layout"] == "cover"
    assert outline["slides"][-1]["layout"] == "closing"


@pytest.mark.asyncio
async def test_presentation_generation_and_export(client: AsyncClient) -> None:
    gen_payload = {
        "title": "Demo Taqdimot",
        "theme": "ezo",
        "language": "uz",
        "slides": [
            {
                "slide_number": 1,
                "layout": "cover",
                "title": "Demo Taqdimot Sarlavhasi",
                "summary": "Qisqacha ta'rif",
                "bullet_hints": ["Muallif: EZO", "Yil: 2026"],
            },
            {
                "slide_number": 2,
                "layout": "bullets",
                "title": "Asosiy Fikrlar",
                "summary": "Muhim yo'nalishlar",
                "bullet_hints": ["Birinchi nuqta", "Ikkinchi nuqta"],
            },
            {
                "slide_number": 3,
                "layout": "closing",
                "title": "E'tiboringiz uchun rahmat",
                "summary": "Savollar bormi?",
                "bullet_hints": ["info@ezo.uz"],
            },
        ],
    }
    resp = await client.post("/api/presentations/generate", json=gen_payload)
    assert resp.status_code == 200
    art = resp.json()
    artifact_id = art["artifact_id"]
    assert art["title"] == "Demo Taqdimot"
    assert art["theme"] == "ezo"
    assert art["slide_count"] == 3
    assert f"/api/artifacts/{artifact_id}/download" in art["pptx_download_url"]
    assert f"/api/artifacts/{artifact_id}/exports/pdf" in art["pdf_download_url"]

    # Inspect presentation
    get_resp = await client.get(f"/api/presentations/{artifact_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["artifact_id"] == artifact_id


@pytest.mark.asyncio
async def test_generated_deck_keeps_the_intake_layouts(client: AsyncClient) -> None:
    """Regression: layouts were checked against theme names, so every slide became bullets."""
    brief = {
        "title": "Layout regressiya",
        "topic": "Maktablarda raqamli ta'lim",
        "audience": "O'qituvchilar",
        "slide_count": 6,
        "theme": "ezo",
        "language": "uz",
        "key_points": ["Bir", "Ikki"],
    }
    outline = (await client.post("/api/presentations/intake", json=brief)).json()
    expected = [slide["layout"] for slide in outline["slides"]]
    assert len(set(expected)) > 2  # the outline really mixes layouts
    resp = await client.post(
        "/api/presentations/generate",
        json={
            "title": brief["title"],
            "theme": "ezo",
            "language": "uz",
            "slides": outline["slides"],
        },
    )
    assert resp.status_code == 200, resp.text
    artifact = (await client.get(f"/api/artifacts/{resp.json()['artifact_id']}")).json()
    assert artifact["current_version"]["generation_metadata"]["layouts"] == expected


@pytest.mark.asyncio
async def test_office_templates_and_document_creation(client: AsyncClient) -> None:
    # 1. List templates
    tmpl_resp = await client.get("/api/office/templates")
    assert tmpl_resp.status_code == 200
    templates = tmpl_resp.json()
    assert len(templates) >= 3
    assert any(t["id"] == "official_letter" for t in templates)
    assert any(t["id"] == "budget_tracker" for t in templates)

    # 2. Create DOCX document
    doc_payload = {
        "title": "Sinov Rasmiy Xati",
        "markdown": (
            "# RASMIY XAT\n\nHurmatli hamkasblar,\n\n"
            "Ushbu xat tizim xavfsizligini tekshirish uchun tuzildi.\n\n"
            "Hurmat bilan,\n**Muallif**"
        ),
        "export_pdf": True,
    }
    doc_resp = await client.post("/api/office/documents", json=doc_payload)
    assert doc_resp.status_code == 200
    doc_art = doc_resp.json()
    assert doc_art["type"] == "document"
    assert "docx" in doc_art["filename"]
    assert "pdf" in doc_art["exports"]

    # 3. Create XLSX spreadsheet
    sheet_payload = {
        "title": "Moliyaviy Hisobot",
        "format": "xlsx",
        "sheets": [
            {
                "name": "Kassa",
                "columns": ["Modda", "Reja", "Haqiqat"],
                "rows": [["Serverlar", 1000, 950], ["Ofis", 500, 480]],
            }
        ],
    }
    sheet_resp = await client.post("/api/office/spreadsheets", json=sheet_payload)
    assert sheet_resp.status_code == 200
    sheet_art = sheet_resp.json()
    assert sheet_art["type"] == "spreadsheet"
    assert "xlsx" in sheet_art["filename"]

    # 4. List office artifacts
    list_resp = await client.get("/api/office/artifacts")
    assert list_resp.status_code == 200
    artifacts = list_resp.json()
    assert len(artifacts) >= 2
    assert any(a["artifact_id"] == doc_art["artifact_id"] for a in artifacts)
    assert any(a["artifact_id"] == sheet_art["artifact_id"] for a in artifacts)
