"""Create and version artifacts.

Rules:
- A version is never modified after it is written. Edits, regenerations and
  restores add a new version (`parent_version_id` records where it came from).
- Content is stored through the StorageProvider under content-addressed keys
  (``artifacts/<user>/<hash[:2]>/<hash>.<ext>``); identical content is stored once.
- The MIME type is decided by EZO from the file extension, never by the caller.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.base import utcnow
from ezo_api.db.models import Artifact, ArtifactVersion
from ezo_api.db.models.artifacts import ARTIFACT_STATUSES, ARTIFACT_TYPES
from ezo_api.knowledge.uploads import extension_of, sanitize_filename, sha256_hex
from ezo_api.storage.base import StorageError, StorageProvider

logger = logging.getLogger(__name__)

MAX_ARTIFACT_BYTES = 200 * 1024 * 1024

# Extensions EZO may store as artifacts, with the MIME type used for downloads.
MIME_BY_EXTENSION: dict[str, str] = {
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json",
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".zip": "application/zip",
    ".py": "text/x-python; charset=utf-8",
    ".ts": "text/plain; charset=utf-8",
    ".tsx": "text/plain; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}
TEXT_EXTENSIONS = frozenset(
    {".md", ".txt", ".csv", ".json", ".html", ".py", ".ts", ".tsx", ".js", ".svg"}
)


class ArtifactError(Exception):
    """A request about an artifact cannot be fulfilled. `message` is safe to show."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class VersionResult:
    artifact: Artifact
    version: ArtifactVersion
    created: bool
    """False when the content was identical to the current version (nothing new stored)."""


def mime_for(filename: str) -> str:
    ext = extension_of(filename)
    if ext not in MIME_BY_EXTENSION:
        allowed = ", ".join(sorted(e.lstrip(".") for e in MIME_BY_EXTENSION))
        raise ArtifactError(
            "unsupported_type",
            f"Artifacts cannot be {ext or 'extensionless'} files. Allowed: {allowed}.",
        )
    return MIME_BY_EXTENSION[ext]


def is_text(filename: str) -> bool:
    return extension_of(filename) in TEXT_EXTENSIONS


class ArtifactService:
    def __init__(self, storage: StorageProvider) -> None:
        self.storage = storage

    async def _store(self, user_id: uuid.UUID, filename: str, data: bytes) -> tuple[str, str]:
        if not data:
            raise ArtifactError("empty", "An artifact version cannot be empty.")
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ArtifactError("too_large", "The artifact is too large to store.")
        content_hash = sha256_hex(data)
        key = f"artifacts/{user_id}/{content_hash[:2]}/{content_hash}{extension_of(filename)}"
        if not await self.storage.exists(key):
            await self.storage.put(key, data)
        return key, content_hash

    async def create(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        *,
        title: str,
        artifact_type: str,
        filename: str,
        data: bytes,
        project_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        created_by_agent: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        generation_metadata: dict[str, Any] | None = None,
        source_references: list[dict[str, Any]] | None = None,
        status: str = "ready",
    ) -> VersionResult:
        if artifact_type not in ARTIFACT_TYPES:
            raise ArtifactError("invalid_type", f"Unknown artifact type: {artifact_type}.")
        if status not in ARTIFACT_STATUSES:
            raise ArtifactError("invalid_status", f"Unknown artifact status: {status}.")
        artifact = Artifact(
            user_id=user_id,
            project_id=project_id,
            conversation_id=conversation_id,
            title=_clean_title(title),
            artifact_type=artifact_type,
            status=status,
            created_by_agent=created_by_agent,
            provider=provider,
            model=model,
            meta=metadata or {},
            source_references=source_references or [],
        )
        session.add(artifact)
        await session.flush()
        return await self.add_version(
            session,
            artifact,
            filename=filename,
            data=data,
            created_by=f"agent:{created_by_agent}" if created_by_agent else "user",
            provider=provider,
            model=model,
            generation_metadata=generation_metadata,
            source_references=source_references,
            change_summary="Created",
        )

    async def current_version(
        self, session: AsyncSession, artifact: Artifact
    ) -> ArtifactVersion | None:
        if artifact.current_version_id is None:
            return None
        return await session.get(ArtifactVersion, artifact.current_version_id)

    async def add_version(
        self,
        session: AsyncSession,
        artifact: Artifact,
        *,
        filename: str,
        data: bytes,
        created_by: str = "user",
        provider: str | None = None,
        model: str | None = None,
        generation_metadata: dict[str, Any] | None = None,
        source_references: list[dict[str, Any]] | None = None,
        change_summary: str | None = None,
        parent_version_id: uuid.UUID | None = None,
    ) -> VersionResult:
        """Add a new immutable version and make it current. Identical content is a no-op."""
        safe_name = sanitize_filename(filename)
        mime_type = mime_for(safe_name)
        current = await self.current_version(session, artifact)
        content_hash = sha256_hex(data) if data else ""
        if (
            current is not None
            and current.content_hash == content_hash
            and current.filename == safe_name
        ):
            return VersionResult(artifact, current, created=False)

        key, content_hash = await self._store(artifact.user_id, safe_name, data)
        last = await session.scalar(
            select(func.max(ArtifactVersion.version_number)).where(
                ArtifactVersion.artifact_id == artifact.id
            )
        )
        version = ArtifactVersion(
            artifact_id=artifact.id,
            version_number=(last or 0) + 1,
            storage_key=key,
            filename=safe_name,
            mime_type=mime_type,
            file_size=len(data),
            content_hash=content_hash,
            provider=provider,
            model=model,
            created_by=created_by,
            change_summary=change_summary,
            parent_version_id=parent_version_id
            if parent_version_id
            else (current.id if current else None),
            generation_metadata=generation_metadata or {},
            source_references=source_references or [],
        )
        session.add(version)
        await session.flush()
        artifact.current_version_id = version.id
        artifact.updated_at = utcnow()
        if provider:
            artifact.provider = provider
        if model:
            artifact.model = model
        if source_references:
            artifact.source_references = source_references
        if artifact.status in ("draft", "generating", "failed"):
            artifact.status = "ready"
        await session.flush()
        return VersionResult(artifact, version, created=True)

    async def versions(
        self, session: AsyncSession, artifact_id: uuid.UUID
    ) -> list[ArtifactVersion]:
        return list(
            (
                await session.scalars(
                    select(ArtifactVersion)
                    .where(ArtifactVersion.artifact_id == artifact_id)
                    .order_by(ArtifactVersion.version_number.desc())
                )
            ).all()
        )

    async def version(
        self, session: AsyncSession, artifact_id: uuid.UUID, number: int
    ) -> ArtifactVersion:
        version = await session.scalar(
            select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == artifact_id, ArtifactVersion.version_number == number
            )
        )
        if version is None:
            raise ArtifactError("not_found", f"Version {number} does not exist.")
        return version

    async def read(self, version: ArtifactVersion) -> bytes:
        try:
            return await self.storage.get(version.storage_key)
        except StorageError as exc:
            raise ArtifactError(
                "missing_file", "The stored file for this version is missing."
            ) from exc

    async def restore(
        self, session: AsyncSession, artifact: Artifact, number: int, *, created_by: str = "user"
    ) -> VersionResult:
        """Make an older version current again by adding it as a NEW version (history is kept)."""
        old = await self.version(session, artifact.id, number)
        current = await self.current_version(session, artifact)
        if current is not None and current.id == old.id:
            return VersionResult(artifact, current, created=False)
        data = await self.read(old)
        last = await session.scalar(
            select(func.max(ArtifactVersion.version_number)).where(
                ArtifactVersion.artifact_id == artifact.id
            )
        )
        version = ArtifactVersion(
            artifact_id=artifact.id,
            version_number=(last or 0) + 1,
            storage_key=old.storage_key,
            filename=old.filename,
            mime_type=old.mime_type,
            file_size=len(data),
            content_hash=old.content_hash,
            provider=old.provider,
            model=old.model,
            created_by=created_by if created_by != "user" else "restore",
            change_summary=f"Restored from version {old.version_number}",
            parent_version_id=old.id,
            generation_metadata=dict(old.generation_metadata or {}),
            source_references=list(old.source_references or []),
        )
        session.add(version)
        await session.flush()
        artifact.current_version_id = version.id
        artifact.updated_at = utcnow()
        await session.flush()
        return VersionResult(artifact, version, created=True)

    async def delete(self, session: AsyncSession, artifact: Artifact) -> None:
        """Delete an artifact and all its versions (explicit user action only)."""
        keys = {v.storage_key for v in await self.versions(session, artifact.id)}
        artifact.current_version_id = None
        await session.flush()
        await session.delete(artifact)
        await session.flush()
        for key in keys:
            still_used = await session.scalar(
                select(func.count())
                .select_from(ArtifactVersion)
                .where(ArtifactVersion.storage_key == key)
            )
            if not still_used:
                try:
                    await self.storage.delete(key)
                except StorageError:
                    logger.warning("Could not delete stored artifact file %s", key)


def _clean_title(title: str) -> str:
    title = " ".join((title or "").split())
    return title[:300] or "Untitled"
