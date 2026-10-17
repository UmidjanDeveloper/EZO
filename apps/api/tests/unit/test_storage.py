from pathlib import Path

import pytest

from ezo_api.storage.base import InvalidStorageKeyError, StorageError
from ezo_api.storage.local import LocalStorageProvider


async def test_put_get_delete(tmp_path: Path) -> None:
    storage = LocalStorageProvider(tmp_path)
    stored = await storage.put("uploads/u1/ab/abc.pdf", b"data")
    assert stored.size == 4
    assert await storage.exists("uploads/u1/ab/abc.pdf")
    assert await storage.get("uploads/u1/ab/abc.pdf") == b"data"
    await storage.delete("uploads/u1/ab/abc.pdf")
    assert not await storage.exists("uploads/u1/ab/abc.pdf")
    with pytest.raises(StorageError):
        await storage.get("uploads/u1/ab/abc.pdf")


@pytest.mark.parametrize(
    "key", ["../escape.txt", "/etc/passwd", "a//b", "a/../../b", "a\\b", "", ".hidden", "a/./b/.."]
)
async def test_unsafe_keys_are_rejected(tmp_path: Path, key: str) -> None:
    storage = LocalStorageProvider(tmp_path)
    with pytest.raises(InvalidStorageKeyError):
        await storage.put(key, b"x")


async def test_symlink_escape_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    storage = LocalStorageProvider(root)
    with pytest.raises(InvalidStorageKeyError):
        await storage.put("link/file.txt", b"x")
