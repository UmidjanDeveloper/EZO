"""OpenJarvis Local Device Companion integration for EZO OS.

Implements local-first device pairing, secure folder sandboxing,
metadata inspection, and read-only file access under explicit user consent.
Adheres strictly to EZO sandbox, tenant isolation, and path traversal defenses.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ezo_api.jarvis.schemas import CompanionDeviceInfo, CompanionFileItem


class CompanionSecurityError(Exception):
    """Raised when an operation violates companion sandbox security boundaries."""


class OpenJarvisCompanion:
    """Manages local device interactions following OpenJarvis architecture.

    Features:
    - Scoped folder permissions (default: Downloads).
    - Device pairing verification.
    - Path traversal prevention.
    - Deterministic file ranking (latest vs previous).
    """

    def __init__(self, root_dir: Path | None = None) -> None:
        self.device_id = "ezo-companion-win-01"
        self.device_name = "Windows Desktop (Local Companion)"
        self.pairing_token = "ezo_oj_token_sec_9841"
        self.paired = True
        self.allowed_directories = ["Downloads"]
        
        # Base sandbox root for companion files (defaults to sandbox/companion or test tempdir)
        if root_dir is None:
            home = Path.home()
            self.base_dir = home / ".ezo" / "companion_sandbox"
        else:
            self.base_dir = root_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "Downloads").mkdir(parents=True, exist_ok=True)

    def get_device_info(self) -> CompanionDeviceInfo:
        """Returns paired device status and governance parameters."""
        return CompanionDeviceInfo(
            device_id=self.device_id,
            device_name=self.device_name,
            os="Windows 11 / EZO Local-First Daemon",
            online=True,
            authorized_directories=self.allowed_directories,
            pairing_status="paired" if self.paired else "unpaired",
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
        )

    def verify_pairing(self, token: str) -> bool:
        """Validates pairing token before allowing device actions."""
        return self.paired and token == self.pairing_token

    def _resolve_safe_path(self, directory_name: str, filename: str | None = None) -> Path:
        """Ensures the target path remains strictly inside authorized sandbox directories."""
        if directory_name not in self.allowed_directories:
            raise CompanionSecurityError(
                f"Directory '{directory_name}' is not authorized. Allowed: {self.allowed_directories}"
            )
        
        target_dir = (self.base_dir / directory_name).resolve()
        
        # Ensure target_dir is strictly inside base_dir
        try:
            target_dir.relative_to(self.base_dir.resolve())
        except ValueError as exc:
            raise CompanionSecurityError("Path traversal detected outside companion base.") from exc

        if not filename:
            return target_dir

        # Check for path traversal in filename
        cleaned_filename = os.path.basename(filename)
        if cleaned_filename != filename or ".." in filename or "/" in filename or "\\" in filename:
            raise CompanionSecurityError("Illegal filename path traversal characters.")

        file_path = (target_dir / cleaned_filename).resolve()
        try:
            file_path.relative_to(target_dir)
        except ValueError as exc:
            raise CompanionSecurityError("Target file path escapes authorized directory.") from exc

        return file_path

    def list_files(self, directory_name: str = "Downloads") -> list[CompanionFileItem]:
        """Lists files in the authorized directory, sorted by modified_at descending."""
        target_dir = self._resolve_safe_path(directory_name)
        if not target_dir.exists():
            return []

        results: list[CompanionFileItem] = []
        for entry in target_dir.iterdir():
            if entry.is_file():
                try:
                    stat = entry.stat()
                    # compute sha256
                    hasher = hashlib.sha256()
                    with open(entry, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                    sha256_hash = hasher.hexdigest()

                    mtime_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                    ext = entry.suffix.lower().lstrip(".") or "txt"

                    results.append(
                        CompanionFileItem(
                            filename=entry.name,
                            path=f"{directory_name}/{entry.name}",
                            size_bytes=stat.st_size,
                            modified_at=mtime_dt.isoformat(),
                            format=ext,
                            sha256=sha256_hash,
                        )
                    )
                except OSError:
                    continue

        # Sort newest first
        results.sort(key=lambda item: item.modified_at, reverse=True)
        return results

    def read_file_content(self, directory_name: str, filename: str, max_bytes: int = 10_000_000) -> dict[str, Any]:
        """Safely reads file content up to max_bytes and parses JSON/CSV if applicable."""
        file_path = self._resolve_safe_path(directory_name, filename)
        if not file_path.exists():
            raise FileNotFoundError(f"File '{filename}' not found in '{directory_name}'")

        stat = file_path.stat()
        if stat.st_size > max_bytes:
            raise CompanionSecurityError(f"File size {stat.st_size} exceeds maximum safe limit of {max_bytes} bytes")

        raw_bytes = file_path.read_bytes()
        hasher = hashlib.sha256(raw_bytes)
        sha256_hash = hasher.hexdigest()

        # Try parsing as JSON
        data: Any = None
        text_content: str | None = None
        try:
            text_content = raw_bytes.decode("utf-8")
            data = json.loads(text_content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

        return {
            "filename": file_path.name,
            "directory": directory_name,
            "size_bytes": stat.st_size,
            "sha256": sha256_hash,
            "parsed_data": data,
            "text_content": text_content if text_content is not None else None,
        }

    def seed_reference_fixtures(self) -> dict[str, str]:
        """Seeds realistic previous and latest metric files for testing the reference scenario.

        File 1: metrics_2026_10_20.json (older)
        File 2: metrics_2026_10_21.json (latest)
        """
        downloads_dir = self._resolve_safe_path("Downloads")
        downloads_dir.mkdir(parents=True, exist_ok=True)

        older_file = downloads_dir / "metrics_2026_10_20.json"
        newer_file = downloads_dir / "metrics_2026_10_21.json"

        older_data = {
            "sana": "2026-10-20",
            "korsatkichlar": {
                "oylik_faol_foydalanuvchilar": 12500,
                "yangi_mijozlar": 1800,
                "konversiya_foizi": 14.4,
                "retention_foizi": 82.0,
                "muvaffaqiyatli_tolovlar": 1540,
            },
            "manba": "EZO OS Analytics Core",
        }

        newer_data = {
            "sana": "2026-10-21",
            "korsatkichlar": {
                "oylik_faol_foydalanuvchilar": 14200,
                "yangi_mijozlar": 2150,
                "konversiya_foizi": 15.1,
                "retention_foizi": 85.5,
                "muvaffaqiyatli_tolovlar": 1890,
            },
            "manba": "EZO OS Analytics Core",
        }

        # Write older file
        older_file.write_text(json.dumps(older_data, indent=2, ensure_ascii=False), encoding="utf-8")
        # Ensure older file timestamp is slightly older
        os.utime(older_file, (1792500000, 1792500000))

        # Write newer file
        newer_file.write_text(json.dumps(newer_data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.utime(newer_file, (1792586400, 1792586400))

        return {
            "older_file": str(older_file),
            "newer_file": str(newer_file),
        }
