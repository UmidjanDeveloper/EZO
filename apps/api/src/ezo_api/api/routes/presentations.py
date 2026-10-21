"""Presentation Maker 2.0 API routes.

Provides:
- Design themes listing
- Brief intake & outline generation
- Structured slide deck generation (PPTX, PDF, HTML preview) using built-in tooling
- Artifact inspection and editing/regeneration
- Source attribution preservation without inventing citations
"""

from __future__ import annotations

import asyncio
from functools import partial
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, ServicesDep, SessionDep, rate_limit
from ezo_api.artifacts.service import ArtifactError
from ezo_api.db.models import Artifact, ArtifactVersion
from ezo_api.documents.render.build import build_deck
from ezo_api.documents.render.spec import DeckSpec, SlideSpec
from ezo_api.documents.render.theme import THEMES
from ezo_api.schemas.presentations import (
    PresentationArtifactOut,
    PresentationBriefIn,
    PresentationGenerateIn,
    PresentationOutlineOut,
    SlideOutlineItem,
    ThemeInfoOut,
)
from ezo_api.tools.document_tools import deck_exports, file_stem

router = APIRouter(
    prefix="/api/presentations",
    tags=["presentations"],
    dependencies=[Depends(rate_limit("default"))],
)


@router.get("/themes")
async def list_themes() -> list[ThemeInfoOut]:
    """Return all available presentation design themes."""
    return [
        ThemeInfoOut(
            name=theme.name,
            dark=theme.dark,
            background=theme.background,
            surface=theme.surface,
            ink=theme.ink,
            accent=theme.accent,
            chart_palette=list(theme.chart),
        )
        for theme in THEMES.values()
    ]


@router.post("/intake")
async def intake_brief(brief: PresentationBriefIn) -> PresentationOutlineOut:
    """Intake presentation brief and generate a structured outline with slide architecture."""
    # Deterministic outline generation based on topic and slide count
    slides: list[SlideOutlineItem] = []
    total = brief.slide_count

    # Slide 1: Cover
    slides.append(
        SlideOutlineItem(
            slide_number=1,
            layout="cover",
            title=brief.title,
            summary=f"{brief.topic[:100]} bo'yicha taqdimot",
            bullet_hints=[brief.audience, "EZO OS Presentation Engine"],
        )
    )

    # Slide 2: Context / Problem
    slides.append(
        SlideOutlineItem(
            slide_number=2,
            layout="problem_solution",
            title="Muammo va dolzarblik",
            summary="Hozirgi holat va mavjud asosiy qiyinchiliklar tahlili",
            bullet_hints=["Asosiy sabablar", "Bozor yoki amaliyotdagi to'siqlar", "Yechimga bo'lgan talab"],
        )
    )

    # Slide 3: Solution / Value
    slides.append(
        SlideOutlineItem(
            slide_number=3,
            layout="big_number",
            title="Asosiy taklif va afzalliklar",
            summary="Taklif etilayotgan yondashuv va erishiladigan natijalar",
            bullet_hints=["Kutilayotgan samaradorlik", "Asosiy farqlovchi omillar"],
        )
    )

    # Key points slides
    current_num = 4
    for pt in brief.key_points:
        if current_num >= total:
            break
        slides.append(
            SlideOutlineItem(
                slide_number=current_num,
                layout="two_column",
                title=f"{pt[:40]}",
                summary=f"{pt} bo'yicha chuqur tahlil va amaliy qadamlar",
                bullet_hints=[f"{pt} - 1-bosqich", f"{pt} - 2-bosqich", "Kutilayotgan natija"],
            )
        )
        current_num += 1

    # Remaining slides up to total
    while current_num < total:
        slides.append(
            SlideOutlineItem(
                slide_number=current_num,
                layout="roadmap" if current_num == total - 1 else "bullets",
                title="Amalga oshirish rejasi va bosqichlar" if current_num == total - 1 else f"Asosiy yo'nalish {current_num}",
                summary="Amaliy harakatlar ketma-ketligi va muddatlar",
                bullet_hints=["1-chorak maqsadlari", "2-chorak maqsadlari", "Monitoring va baholash"],
            )
        )
        current_num += 1

    # Closing slide
    slides.append(
        SlideOutlineItem(
            slide_number=total,
            layout="closing",
            title="E'tiboringiz uchun rahmat!",
            summary="Savollar va muhokama",
            bullet_hints=["Aloqa uchun ma'lumotlar", "Keyingi qadamlar"],
        )
    )

    return PresentationOutlineOut(
        title=brief.title,
        theme=brief.theme if brief.theme in THEMES else "ezo",
        language=brief.language,
        slide_count=len(slides),
        slides=slides,
    )


@router.post("/generate")
async def generate_presentation(
    payload: PresentationGenerateIn,
    db: SessionDep,
    services: ServicesDep,
    user: CurrentUser,
) -> PresentationArtifactOut:
    """Generate PPTX presentation artifact from outline or structured brief."""
    theme_name = payload.theme if payload.theme in THEMES else "ezo"

    # Convert slides or create default structure
    slide_specs: list[SlideSpec] = []
    if payload.slides:
        for item in payload.slides:
            slide_specs.append(
                SlideSpec(
                    layout=item.layout if item.layout in THEMES else "bullets",
                    title=item.title,
                    subtitle=item.summary,
                    bullets=item.bullet_hints or [item.summary],
                )
            )
    else:
        slide_specs = [
            SlideSpec(layout="cover", title=payload.title, subtitle="Taqdimot"),
            SlideSpec(layout="bullets", title="Kirish", bullets=["Asosiy maqsad", "Kutilayotgan natijalar"]),
            SlideSpec(layout="closing", title="Rahmat!", subtitle="Savollar bormi?"),
        ]

    deck = DeckSpec(
        title=payload.title,
        theme=theme_name,
        aspect_ratio="16:9",
        language=payload.language,
        slides=slide_specs,
    )

    try:
        build = await asyncio.to_thread(partial(build_deck, deck))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to build presentation deck: {exc}")

    stem = file_stem(deck.title, "presentation")
    exports = deck_exports(build, stem)

    metadata: dict[str, Any] = {
        "slides": len(build.plans),
        "theme": build.theme.name,
        "aspect_ratio": deck.aspect_ratio,
        "language": deck.language,
        "qa": build.qa.to_dict(),
        "fixes": build.fixes,
    }

    try:
        result = await services.artifacts.create(
            db,
            user.id,
            title=deck.title,
            artifact_type="presentation",
            filename=f"{stem}.pptx",
            data=build.pptx,
            project_id=None,
            conversation_id=payload.conversation_id,
            created_by_agent="presentation",
            generation_metadata=metadata,
            exports=exports,
        )
        await db.commit()
    except ArtifactError as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    artifact_id = result.artifact.id
    return PresentationArtifactOut(
        artifact_id=artifact_id,
        title=result.artifact.title,
        theme=theme_name,
        slide_count=len(build.plans),
        pptx_download_url=f"/api/artifacts/{artifact_id}/download",
        pdf_download_url=f"/api/artifacts/{artifact_id}/exports/pdf",
        html_preview_url=f"/api/artifacts/{artifact_id}/exports/html",
        qa_report=build.qa.to_dict(),
    )


@router.get("/{artifact_id}")
async def get_presentation(
    artifact_id: uuid.UUID, db: SessionDep, user: CurrentUser
) -> PresentationArtifactOut:
    """Get presentation artifact metadata, download links, and QA report."""
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None or artifact.user_id != user.id or artifact.artifact_type != "presentation":
        raise HTTPException(status_code=404, detail="Presentation artifact not found.")

    version = (
        await db.scalars(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact.id)
            .order_by(ArtifactVersion.version_number.desc())
            .limit(1)
        )
    ).first()

    meta = (version.generation_metadata if version else {}) or {}
    return PresentationArtifactOut(
        artifact_id=artifact.id,
        title=artifact.title,
        theme=str(meta.get("theme", "ezo")),
        slide_count=int(meta.get("slides", 0)),
        pptx_download_url=f"/api/artifacts/{artifact.id}/download",
        pdf_download_url=f"/api/artifacts/{artifact.id}/exports/pdf",
        html_preview_url=f"/api/artifacts/{artifact.id}/exports/html",
        qa_report=meta.get("qa") or {},
    )
