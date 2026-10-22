"""Real filesystem writes; synchronize the rename boundary, not filesystem mocks."""

import asyncio
import os
import threading

import pytest

from ezo_api.storage.base import StorageError
from ezo_api.storage.local import LocalStorageProvider


async def test_identical_concurrent_puts_do_not_share_a_temporary_path(tmp_path, monkeypatch):
    store = LocalStorageProvider(tmp_path)
    barrier = threading.Barrier(2, timeout=5)
    actual_replace = os.replace

    def synchronized_replace(source, destination):
        barrier.wait()
        return actual_replace(source, destination)

    monkeypatch.setattr(os, "replace", synchronized_replace)
    results = await asyncio.gather(
        store.put("owned/object.txt", b"same content"),
        store.put("owned/object.txt", b"same content"),
    )
    assert len(results) == 2
    if os.name == "posix":
        assert (tmp_path / "owned/object.txt").stat().st_mode & 0o077 == 0
    assert await store.get("owned/object.txt") == b"same content"
    assert [p.name for p in (tmp_path / "owned").iterdir()] == ["object.txt"]


async def test_failed_replace_preserves_previous_file_and_removes_partial_temp(
    tmp_path, monkeypatch
):
    store = LocalStorageProvider(tmp_path)
    await store.put("owned/object.txt", b"previous")

    def unavailable_replace(source, destination):
        raise OSError("controlled rename failure")

    monkeypatch.setattr(os, "replace", unavailable_replace)
    with pytest.raises(StorageError):
        await store.put("owned/object.txt", b"replacement")
    assert await store.get("owned/object.txt") == b"previous"
    assert [p.name for p in (tmp_path / "owned").iterdir()] == ["object.txt"]
