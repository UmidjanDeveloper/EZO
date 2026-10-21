"""StorageProvider interface.

The rest of EZO only knows *storage keys* (like ``uploads/<user>/<hash>.pdf``),
never filesystem paths, so the backend can move to S3-compatible storage
without touching callers.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")


class StorageError(Exception):
    pass


class InvalidStorageKeyError(StorageError):
    pass


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int


def validate_key(key: str) -> str:
    """Accept only simple relative keys: no '..', no absolute paths, no backslashes."""
    if not _KEY_RE.match(key) or ".." in key.split("/") or "//" in key:
        raise InvalidStorageKeyError(f"Invalid storage key: {key!r}")
    return key


class StorageProvider(ABC):
    name: str

    async def aclose(self) -> None:
        """Release provider connections (local storage has none)."""
        return None

    @abstractmethod
    async def put(self, key: str, data: bytes) -> StoredObject: ...

    @abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...
