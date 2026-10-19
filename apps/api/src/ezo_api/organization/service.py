"""Loading an organization profile with its files for drafting and rendering."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import OrganizationAsset, OrganizationProfile
from ezo_api.storage.base import StorageError, StorageProvider
from ezo_api.writing.service import OrgFacts

MAX_EXAMPLES = 2
EXAMPLE_PROMPT_CHARS = 3_000


async def default_profile(session: AsyncSession, user_id: uuid.UUID) -> OrganizationProfile | None:
    return await session.scalar(
        select(OrganizationProfile)
        .where(OrganizationProfile.user_id == user_id)
        .order_by(OrganizationProfile.is_default.desc(), OrganizationProfile.updated_at.desc())
        .limit(1)
    )


async def _read(storage: StorageProvider, key: str | None) -> bytes | None:
    if not key:
        return None
    try:
        return await storage.get(key)
    except StorageError:
        return None  # a missing file must not break drafting


async def load_facts(
    session: AsyncSession,
    storage: StorageProvider,
    user_id: uuid.UUID,
    *,
    doc_key: str | None = None,
    official: bool = True,
) -> tuple[OrgFacts | None, OrganizationProfile | None]:
    """The default profile as OrgFacts, with the logo, the template for `doc_key` (a
    template for that type first, else a general one for official layouts) and up to two
    examples (same type first)."""
    profile = await default_profile(session, user_id)
    if profile is None:
        return None, None
    assets = (
        await session.scalars(
            select(OrganizationAsset)
            .where(
                OrganizationAsset.organization_id == profile.id,
                OrganizationAsset.user_id == user_id,
            )
            .order_by(OrganizationAsset.created_at.desc())
        )
    ).all()
    templates = [a for a in assets if a.kind == "template"]
    template = next((a for a in templates if doc_key and a.doc_type == doc_key), None)
    if template is None and official:
        template = next((a for a in templates if not a.doc_type), None)
    examples = sorted(
        (a for a in assets if a.kind == "example" and a.text_excerpt),
        key=lambda a: 0 if doc_key and a.doc_type == doc_key else (1 if not a.doc_type else 2),
    )
    examples = [a for a in examples if not a.doc_type or a.doc_type == doc_key][:MAX_EXAMPLES]
    facts = OrgFacts(
        name=profile.name,
        department=profile.department or "",
        address=profile.address or "",
        phone=profile.phone or "",
        email=profile.email or "",
        website=profile.website or "",
        head_position=profile.head_position or "",
        head_name=profile.head_name or "",
        letterhead=profile.letterhead or "",
        style_notes=profile.style_notes or "",
        terminology={str(k): str(v) for k, v in (profile.terminology or {}).items()},
        formatting=dict(profile.formatting or {}),
        logo=await _read(storage, profile.logo_key),
        template=await _read(storage, template.storage_key) if template else None,
        template_title=template.title if template else "",
        examples=[(a.title, (a.text_excerpt or "")[:EXAMPLE_PROMPT_CHARS]) for a in examples],
    )
    return facts, profile
