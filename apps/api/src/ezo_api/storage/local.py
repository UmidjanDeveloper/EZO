"""Local filesystem storage (development and single-machine installs)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from ezo_api.storage.base import (
    InvalidStorageKeyError,
    StorageError,
    StorageProvider,
    StoredObject,
    validate_key,
)


class LocalStorageProvider(StorageProvider):
    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        # Defence in depth against path traversal (symlinks, odd keys).
        if not path.is_relative_to(self.root):
            raise InvalidStorageKeyError(f"Key escapes storage root: {key!r}")
        return path

    async def put(self, key: str, data: bytes) -> StoredObject:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".tmp")
            temp.write_bytes(data)
            os.replace(temp, path)  # atomic on the same filesystem

        try:
            await asyncio.to_thread(write)
        except OSError as exc:
            raise StorageError(f"Could not write {key}: {exc}") from exc
        return StoredObject(key=key, size=len(data))

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise StorageError(f"File not found in storage: {key}") from exc

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, True)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._path(key).is_file)
