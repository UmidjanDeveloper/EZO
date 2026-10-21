"""Documents & Office Workspace API routes.

Provides safe document and spreadsheet authoring:
- Document templates (Official letter, CV/resume, Memorandum, Budget, Invoice)
- Safe DOCX creation with optional PDF export
- Safe XLSX spreadsheet generation from structured table data
- Office artifacts listing and download links
- Strict safety: no macros, no untrusted code execution, no cross-user leakage
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.artifacts.service import ArtifactError
from ezo_api.db.models import Artifact, ArtifactVersion
from ezo_api.documents.markdown_io import parse_markdown
from ezo_api.documents.model import word_count
from ezo_api.documents.spreadsheet.writer import Sheet, render_csv, render_xlsx
from ezo_api.schemas.office import (
    DocumentCreateIn,
    OfficeArtifactOut,
    OfficeTemplateOut,
    SpreadsheetCreateIn,
)
from ezo_api.tools.document_tools import (
    _EXPORT_NAMES,
    file_stem,
    render_document,
)

router = APIRouter(
    prefix="/api/office",
    tags=["office"],
    dependencies=[Depends(rate_limit("default"))],
)

TEMPLATES: list[OfficeTemplateOut] = [
    OfficeTemplateOut(
        id="official_letter",
        title="Rasmiy xat (Official Letter)",
        type="docx",
        category="Ish yuritish",
        description="Vazirliklar, idoralar va tashkilotlarga yuboriladigan standart rasmiy xat shabloni.",
        sample_content={
            "markdown": (
                "# RASMIY XAT\n\n"
                "**Kimga:** Tashkilot rahbariyatiga\n\n"
                "**Kimdan:** EZO OS loyihasi jamoasi\n\n"
                "**Mavzu:** Hamkorlik aloqalarini o'rnatish to'g'risida\n\n"
                "Hurmatli hamkasblar!\n\n"
                "Mazkur xat orqali Sizning tashkilotingiz bilan axborot texnologiyalari va ta'lim sohasida o'zaro hamkorlikni rivojlantirish istagini bildiramiz.\n\n"
                "Hurmat bilan,\n\n**Bosh ijrochi direktor**"
            )
        },
    ),
    OfficeTemplateOut(
        id="resume_cv",
        title="Professional CV / Rezyume",
        type="docx",
        category="Karyera",
        description="Zamonaviy, xalqaro standartlarga mos ikki ustunli rezyume.",
        sample_content={
            "markdown": (
                "# SHAXSIY REZYUME (CV)\n\n"
                "## Aloqa ma'lumotlari\n"
                "- Telefon: +998 90 123 45 67\n"
                "- Email: nomzod@example.com\n"
                "- Manzil: Toshkent shahar\n\n"
                "## Ish tajribasi\n"
                "### Katta dasturiy injener · Tech Corp (2022 - hozirgacha)\n"
                "- Yuqori yuklamali mikroxizmatlar arxitekturasini ishlab chiqish.\n"
                "- AI agentlari integratsiyasini boshqarish.\n\n"
                "## Ma'lumoti\n"
                "- Bakalavr: Axborot texnologiyalari, Toshkent axborot texnologiyalari universiteti (2018 - 2022)"
            )
        },
    ),
    OfficeTemplateOut(
        id="budget_tracker",
        title="Oylik byudjet va xarajatlar",
        type="xlsx",
        category="Moliya",
        description="Kompaniya yoki shaxsiy byudjet tushumlari va xarajatlari hisoboti.",
        sample_content={
            "columns": ["Kategoriya", "Reja (UZS)", "Haqiqiy (UZS)", "Farq (UZS)", "Holat"],
            "rows": [
                ["Server infratuzilmasi", 15000000, 14200000, -800000, "Tejaldi"],
                ["Ish haqi fondi", 85000000, 85000000, 0, "Reja bo'yicha"],
                ["Marketing va reklama", 20000000, 21500000, 1500000, "Ortiqcha"],
                ["Ofis xarajatlari", 10000000, 9500000, -500000, "Tejaldi"],
            ],
        },
    ),
    OfficeTemplateOut(
        id="services_invoice",
        title="Xizmatlar hisob-fakturasi",
        type="xlsx",
        category="Savdo",
        description="Bajarilgan ishlar va ko'rsatilgan xizmatlar uchun hisob-faktura jadvali.",
        sample_content={
            "columns": ["Xizmat nomi", "Miqdori", "Birlik narxi (UZS)", "Jami (UZS)"],
            "rows": [
                ["Dasturiy ta'minot ishlab chiqish", 160, 250000, 40000000],
                ["Texnik qo'llab-quvvatlash", 1, 5000000, 5000000],
                ["Xavfsizlik auditi", 1, 15000000, 15000000],
            ],
        },
    ),
]


@router.get("/templates")
async def list_templates() -> list[OfficeTemplateOut]:
    """Return available safe document and spreadsheet templates."""
    return TEMPLATES


@router.post("/documents")
async def create_document_endpoint(
    payload: DocumentCreateIn,
    db: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> OfficeArtifactOut:
    """Create a DOCX document artifact with optional PDF export."""
    files = await asyncio.to_thread(
        render_document, payload.markdown, payload.title, "docx", None
    )
    stem = file_stem(payload.title, "document")
    exports = {
        _EXPORT_NAMES[ext]: (f"{stem}.{ext}", data)
        for ext, data in files.items()
        if ext != "docx" and ext in _EXPORT_NAMES
    }
    spec = parse_markdown(payload.markdown, title=payload.title)
    metadata: dict[str, Any] = {
        "words": word_count(spec),
        "format": "docx",
        "has_pdf": "pdf" in files,
    }

    try:
        result = await services.artifacts.create(
            db,
            user.id,
            title=payload.title,
            artifact_type="document",
            filename=f"{stem}.docx",
            data=files["docx"],
            project_id=None,
            conversation_id=payload.conversation_id,
            created_by_agent="document",
            generation_metadata=metadata,
            exports=exports,
        )
        await db.commit()
    except ArtifactError as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    artifact_id = result.artifact.id
    export_links = {
        ext: f"/api/artifacts/{artifact_id}/exports/{ext}"
        for ext in exports
    }
    return OfficeArtifactOut(
        artifact_id=artifact_id,
        title=result.artifact.title,
        type="document",
        filename=f"{stem}.docx",
        download_url=f"/api/artifacts/{artifact_id}/download",
        exports=export_links,
        created_at=str(result.artifact.created_at),
    )


@router.post("/spreadsheets")
async def create_spreadsheet_endpoint(
    payload: SpreadsheetCreateIn,
    db: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> OfficeArtifactOut:
    """Create an XLSX or CSV spreadsheet artifact."""
    sheets = [Sheet(s.name, s.columns, [list(r) for r in s.rows]) for s in payload.sheets]
    stem = file_stem(payload.title, "spreadsheet")
    if payload.format == "xlsx":
        data = await asyncio.to_thread(render_xlsx, sheets, payload.title)
        exports = {"csv": (f"{stem}.csv", render_csv(sheets[0]))} if len(sheets) == 1 else {}
    else:
        data = render_csv(sheets[0])
        exports = {"xlsx": (f"{stem}.xlsx", await asyncio.to_thread(render_xlsx, sheets))}

    rows_count = sum(len(s.rows) for s in sheets)
    metadata: dict[str, Any] = {"sheets": len(sheets), "rows": rows_count, "format": payload.format}

    try:
        result = await services.artifacts.create(
            db,
            user.id,
            title=payload.title,
            artifact_type="spreadsheet",
            filename=f"{stem}.{payload.format}",
            data=data,
            project_id=None,
            conversation_id=payload.conversation_id,
            created_by_agent="document",
            generation_metadata=metadata,
            exports=exports,
        )
        await db.commit()
    except ArtifactError as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    artifact_id = result.artifact.id
    export_links = {
        ext: f"/api/artifacts/{artifact_id}/exports/{ext}"
        for ext in exports
    }
    return OfficeArtifactOut(
        artifact_id=artifact_id,
        title=result.artifact.title,
        type="spreadsheet",
        filename=f"{stem}.{payload.format}",
        download_url=f"/api/artifacts/{artifact_id}/download",
        exports=export_links,
        created_at=str(result.artifact.created_at),
    )


@router.get("/artifacts")
async def list_office_artifacts(
    db: SessionDep, user: CurrentUser
) -> list[OfficeArtifactOut]:
    """List all document and spreadsheet artifacts owned by the user."""
    rows = await db.scalars(
        select(Artifact)
        .where(
            Artifact.user_id == user.id,
            Artifact.artifact_type.in_(["document", "spreadsheet", "presentation"]),
        )
        .order_by(Artifact.created_at.desc())
        .limit(50)
    )
    items: list[OfficeArtifactOut] = []
    for art in rows.all():
        ext = "docx" if art.artifact_type == "document" else ("xlsx" if art.artifact_type == "spreadsheet" else "pptx")
        stem = file_stem(art.title, "office")
        items.append(
            OfficeArtifactOut(
                artifact_id=art.id,
                title=art.title,
                type=art.artifact_type,
                filename=f"{stem}.{ext}",
                download_url=f"/api/artifacts/{art.id}/download",
                exports={},
                created_at=str(art.created_at),
            )
        )
    return items
