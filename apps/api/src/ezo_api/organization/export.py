"""Export of an organization profile: one ZIP with profile.json and its files."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

from ezo_api.db.models import OrganizationAsset, OrganizationProfile
from ezo_api.storage.base import StorageError, StorageProvider

FIELDS = (
    "name", "org_type", "department", "address", "phone", "email", "website",
    "head_position", "head_name", "letterhead", "style_notes", "terminology",
    "formatting", "is_default",
)  # fmt: skip


async def build_export(
    profile: OrganizationProfile, assets: list[OrganizationAsset], storage: StorageProvider
) -> bytes:
    manifest: dict[str, Any] = {
        "format": "ezo-organization-profile",
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "profile": {name: getattr(profile, name) for name in FIELDS},
        "logo": None,
        "files": [],
        "missing": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if profile.logo_key:
            try:
                archive.writestr("logo.png", await storage.get(profile.logo_key))
                manifest["logo"] = "logo.png"
            except StorageError:
                manifest["missing"].append("logo.png")
        counts: dict[str, int] = {}
        for asset in assets:
            counts[asset.kind] = counts.get(asset.kind, 0) + 1
            path = f"{asset.kind}s/{counts[asset.kind]:02d}-{asset.filename}"
            try:
                archive.writestr(path, await storage.get(asset.storage_key))
            except StorageError:
                manifest["missing"].append(path)
                continue
            manifest["files"].append(
                {
                    "path": path,
                    "kind": asset.kind,
                    "title": asset.title,
                    "doc_type": asset.doc_type,
                    "sha256": asset.sha256,
                }
            )
        archive.writestr("profile.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buffer.getvalue()
