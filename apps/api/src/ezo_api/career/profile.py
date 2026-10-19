"""Career profile schema, the facts block for prompts, and a CV built directly from the
profile (no model, so nothing can be added)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.translation.translit import to_cyrillic


class Experience(BaseModel):
    role: str = Field(min_length=1, max_length=200)
    organization: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=200)
    start: str = Field(default="", max_length=20)
    end: str = Field(default="", max_length=20)
    achievements: list[str] = Field(default_factory=list, max_length=15)


class Education(BaseModel):
    institution: str = Field(min_length=1, max_length=200)
    degree: str = Field(default="", max_length=200)
    field: str = Field(default="", max_length=200)
    start: str = Field(default="", max_length=20)
    end: str = Field(default="", max_length=20)
    notes: str = Field(default="", max_length=500)


class LanguageSkill(BaseModel):
    language: str = Field(min_length=1, max_length=50)
    level: str = Field(default="", max_length=50)


class Certificate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(default="", max_length=200)
    year: str = Field(default="", max_length=10)


class CareerProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    links: list[str] = Field(default_factory=list, max_length=10)
    summary: str | None = Field(default=None, max_length=2_000)
    experience: list[Experience] = Field(default_factory=list, max_length=30)
    education: list[Education] = Field(default_factory=list, max_length=15)
    skills: list[str] = Field(default_factory=list, max_length=60)
    languages: list[LanguageSkill] = Field(default_factory=list, max_length=15)
    certificates: list[Certificate] = Field(default_factory=list, max_length=30)


LABELS = {
    "uz": {"summary": "Qisqacha", "experience": "Ish tajribasi", "education": "Ma'lumoti",
           "skills": "Ko'nikmalar", "languages": "Tillar", "certificates": "Sertifikatlar",
           "present": "hozirgacha"},
    "ru": {"summary": "О себе", "experience": "Опыт работы", "education": "Образование",
           "skills": "Навыки", "languages": "Языки", "certificates": "Сертификаты",
           "present": "по настоящее время"},
    "en": {"summary": "Summary", "experience": "Experience", "education": "Education",
           "skills": "Skills", "languages": "Languages", "certificates": "Certificates",
           "present": "present"},
}  # fmt: skip


def _period(start: str, end: str, present: str) -> str:
    if not start and not end:
        return ""
    return f"{start or '?'} – {end or present}"


def facts_text(profile: CareerProfileIn) -> str:
    """The profile as plain facts for a model prompt and for checking a draft's numbers."""
    lines = [f"Name: {profile.full_name}"]
    for label, value in (
        ("Headline", profile.headline),
        ("E-mail", profile.email),
        ("Phone", profile.phone),
        ("Location", profile.location),
        ("Summary", profile.summary),
    ):
        if value:
            lines.append(f"{label}: {value}")
    if profile.links:
        lines.append("Links: " + ", ".join(profile.links))
    for job in profile.experience:
        period = _period(job.start, job.end, "present")
        lines.append(
            f"Experience: {job.role}"
            + (f", {job.organization}" if job.organization else "")
            + (f" ({period})" if period else "")
            + (": " + "; ".join(job.achievements) if job.achievements else "")
        )
    for study in profile.education:
        period = _period(study.start, study.end, "present")
        lines.append(
            "Education: "
            + ", ".join(v for v in (study.degree, study.field, study.institution) if v)
            + (f" ({period})" if period else "")
            + (f"; {study.notes}" if study.notes else "")
        )
    if profile.skills:
        lines.append("Skills: " + ", ".join(profile.skills))
    if profile.languages:
        lines.append(
            "Languages: " + ", ".join(f"{x.language} {x.level}".strip() for x in profile.languages)
        )
    for cert in profile.certificates:
        lines.append(
            "Certificate: " + ", ".join(v for v in (cert.name, cert.issuer, cert.year) if v)
        )
    return "\n".join(lines)


def cv_markdown(profile: CareerProfileIn, language: str = "uz") -> str:
    """A CV in Markdown, exactly from the profile (headings in the chosen language)."""
    t = LABELS.get("uz" if language.startswith("uz") else language, LABELS["en"])
    lines = [f"# {profile.full_name}", ""]
    if profile.headline:
        lines += [f"**{profile.headline}**", ""]
    contacts = [v for v in (profile.email, profile.phone, profile.location) if v] + profile.links
    if contacts:
        lines += [" · ".join(contacts), ""]
    if profile.summary:
        lines += [f"## {t['summary']}", "", profile.summary, ""]
    if profile.experience:
        lines += [f"## {t['experience']}", ""]
        for job in profile.experience:
            period = _period(job.start, job.end, t["present"])
            head = f"**{job.role}**" + (f" — {job.organization}" if job.organization else "")
            tail = ", ".join(v for v in (job.location, period) if v)
            lines += [head + (f" ({tail})" if tail else ""), ""]
            lines += [f"- {a}" for a in job.achievements] + ([""] if job.achievements else [])
    if profile.education:
        lines += [f"## {t['education']}", ""]
        for study in profile.education:
            period = _period(study.start, study.end, t["present"])
            what = ", ".join(v for v in (study.degree, study.field) if v)
            lines.append(
                f"**{study.institution}**"
                + (f" — {what}" if what else "")
                + (f" ({period})" if period else "")
            )
            lines += ([study.notes] if study.notes else []) + [""]
    if profile.skills:
        lines += [f"## {t['skills']}", "", ", ".join(profile.skills), ""]
    if profile.languages:
        lines += [f"## {t['languages']}", ""]
        lines += [
            f"- {x.language}" + (f" — {x.level}" if x.level else "") for x in profile.languages
        ]
        lines.append("")
    if profile.certificates:
        lines += [f"## {t['certificates']}", ""]
        for cert in profile.certificates:
            lines.append(
                f"- {cert.name}" + "".join(f", {v}" for v in (cert.issuer, cert.year) if v)
            )
        lines.append("")
    markdown = "\n".join(lines).strip() + "\n"
    return to_cyrillic(markdown) if language == "uz-cyrl" else markdown


def from_row(row: Any) -> CareerProfileIn:
    return CareerProfileIn.model_validate(
        {
            "full_name": row.full_name,
            "headline": row.headline,
            "email": row.email,
            "phone": row.phone,
            "location": row.location,
            "links": row.links or [],
            "summary": row.summary,
            "experience": row.experience or [],
            "education": row.education or [],
            "skills": row.skills or [],
            "languages": row.languages or [],
            "certificates": row.certificates or [],
        }
    )


async def load_profile(session: AsyncSession, user_id: uuid.UUID) -> CareerProfileIn | None:
    from ezo_api.db.models import CareerProfile

    row = await session.scalar(select(CareerProfile).where(CareerProfile.user_id == user_id))
    return from_row(row) if row is not None else None
