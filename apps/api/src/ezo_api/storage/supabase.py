"""Private Supabase object storage. No public URLs, local fallback or implicit overwrite."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from urllib.parse import quote, urlsplit

import httpx

from ezo_api.storage.base import StorageError, StorageProvider, StoredObject, validate_key


class StorageUnavailableError(StorageError):
    """Availability/auth failures must never be mistaken for a missing object."""


class StorageLimitError(StorageUnavailableError):
    pass


def validate_endpoint(url: str, bucket: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not re.fullmatch(r"[a-z0-9]{20}\.supabase\.co", parsed.netloc)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,62}", bucket)
    ):
        raise ValueError("Use the exact HTTPS Supabase project origin and a simple bucket name.")
    return url.rstrip("/")


class SupabaseStorageProvider(StorageProvider):
    name = "supabase"

    def __init__(
        self,
        url: str,
        key: str,
        bucket: str,
        *,
        max_bytes: int = 5_000_000,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        origin = validate_endpoint(url, bucket)
        if len(key.strip()) < 32 or not 1 <= max_bytes <= 5_000_000:
            raise ValueError("Storage requires a server credential and a bounded object size.")
        self.bucket = bucket
        self.max_bytes = max_bytes
        self._slots = asyncio.Semaphore(2)
        self._client = httpx.AsyncClient(
            base_url=origin + "/storage/v1/",
            headers={
                "apikey": key.strip(),
                "Authorization": "Bearer " + key.strip(),
                "Accept-Encoding": "identity",
            },
            timeout=httpx.Timeout(10, connect=5, pool=5),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
            follow_redirects=False,
            transport=transport,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        cap: int | None = None,
        content_type: str = "application/octet-stream",
    ) -> tuple[int, bytes]:
        # Bound the entire operation, including slot acquisition and streamed bodies.
        try:
            async with (
                asyncio.timeout(20),
                self._slots,
                self._client.stream(
                    method,
                    path,
                    content=data,
                    headers={"Content-Type": content_type, "x-upsert": "false"},
                ) as response,
            ):
                status = response.status_code
                if status not in (200, 201, 204):
                    # Never echo provider bodies, URLs, headers or credential-bearing errors.
                    return status, b""
                limit = self.max_bytes if cap is None else cap
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65_536):
                    if len(body) + len(chunk) > limit:
                        raise StorageLimitError("Stored object exceeds the configured limit.")
                    body.extend(chunk)
                return status, bytes(body)
        except (httpx.HTTPError, TimeoutError):
            raise StorageUnavailableError("Private storage is unavailable; retry later.") from None

    def _object(self, key: str) -> str:
        validate_key(key)
        if "." in key.split("/") or key.endswith("/"):
            raise StorageError("Storage keys must identify an object without dot segments.")
        return f"object/{self.bucket}/{quote(key, safe='/')}"

    async def check_private(self) -> None:
        status, body = await self._request("GET", "bucket/" + self.bucket, cap=16_384)
        try:
            info = json.loads(body)
            valid = (
                status == 200
                and info["id"] == self.bucket
                and info["public"] is False
                and type(info["file_size_limit"]) is int
                and 0 < info["file_size_limit"] <= self.max_bytes
            )
        except (ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            raise StorageUnavailableError("A private bucket with a bounded file limit is required.")

    async def preflight(self) -> None:
        from uuid import uuid4

        key = "healthchecks/" + uuid4().hex
        data = b"ezo-private-storage-check"
        await self.put(key, data)
        try:
            if await self.get(key) != data:
                raise StorageUnavailableError("Private storage integrity check failed.")
        finally:
            await self.delete(key)
        if await self.exists(key):
            raise StorageUnavailableError("Private storage cleanup check failed.")

    @staticmethod
    def _verify_artifact_hash(key: str, data: bytes) -> None:
        # ArtifactService defines these names from SHA256 of exact object bytes.
        name = key.rsplit("/", 1)[-1]
        match = re.fullmatch(r"([0-9a-f]{64})(?:\.[a-z0-9]+)?", name)
        if key.startswith("artifacts/") and match and hashlib.sha256(data).hexdigest() != match[1]:
            raise StorageUnavailableError("Stored artifact integrity verification failed.")

    async def put(self, key: str, data: bytes) -> StoredObject:
        path = self._object(key)
        if len(data) > self.max_bytes:
            raise StorageLimitError("Object exceeds the configured storage limit.")
        self._verify_artifact_hash(key, data)
        await self.check_private()
        status, _ = await self._request("POST", path, data=data, cap=16_384)
        if status == 409:
            if await self.get(key) != data:
                raise StorageUnavailableError(
                    "An immutable storage object conflicts with this write."
                )
        elif status not in (200, 201):
            raise StorageUnavailableError("Private storage write was not acknowledged.")
        return StoredObject(key, len(data))

    async def get(self, key: str) -> bytes:
        path = self._object(key)
        await self.check_private()
        status, data = await self._request("GET", path)
        if status == 404:
            raise StorageError("Stored object not found.")
        if status != 200:
            raise StorageUnavailableError("Private storage read is unavailable.")
        self._verify_artifact_hash(key, data)
        return data

    async def delete(self, key: str) -> None:
        self._object(key)
        await self.check_private()
        status, _ = await self._request(
            "DELETE",
            f"object/{self.bucket}",
            data=json.dumps({"prefixes": [key]}).encode(),
            content_type="application/json",
            cap=16_384,
        )
        if status != 200:
            raise StorageUnavailableError("Private storage deletion was not acknowledged.")

    async def exists(self, key: str) -> bool:
        path = self._object(key)
        await self.check_private()
        status, _ = await self._request("HEAD", path, cap=0)
        if status == 404:
            return False
        if status != 200:
            raise StorageUnavailableError("Private storage existence check is unavailable.")
        return True

    async def aclose(self) -> None:
        await self._client.aclose()
