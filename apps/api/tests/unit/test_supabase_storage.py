"""Adversarial private Storage REST contracts; no credentials or live service."""

import httpx
import pytest

from ezo_api.deployment import DeploymentError, validate_production
from ezo_api.storage.base import StorageError
from ezo_api.storage.supabase import (
    StorageLimitError,
    StorageUnavailableError,
    SupabaseStorageProvider,
    validate_endpoint,
)
from tests.integration.test_free_beta import KEY, URL, CloudFixture, free_settings


@pytest.mark.parametrize(
    "url",
    [
        "http://abcdefghijklmnopqrst.supabase.co",
        "https://evil.test",
        URL + "?key=secret",
        URL + "/path",
        "https://user:secret@abcdefghijklmnopqrst.supabase.co",
        URL + ":443",
    ],
)
def test_endpoint_is_exact_and_cannot_be_an_ssrf_destination(url):
    with pytest.raises(ValueError):
        validate_endpoint(url, "ezo-private")


@pytest.mark.parametrize(
    "key",
    [
        "../secret",
        "user/../other",
        "user/./secret",
        "user//secret",
        "user\\secret",
        "user/x?token=secret",
        "user/",
    ],
)
async def test_unsafe_keys_never_reach_network(key):
    cloud = CloudFixture()
    provider = cloud.provider()
    try:
        with pytest.raises(StorageError):
            await provider.get(key)
        assert cloud.calls == []
    finally:
        await provider.aclose()


async def test_immutable_idempotency_private_check_delete_and_recreation():
    cloud = CloudFixture()
    p = cloud.provider()
    try:
        await p.preflight()
        assert cloud.objects == {}
        await p.put("uploads/user/hash.txt", b"original")
        await p.put("uploads/user/hash.txt", b"original")
        with pytest.raises(StorageUnavailableError):
            await p.put("uploads/user/hash.txt", b"different")
        assert await p.get("uploads/user/hash.txt") == b"original"
        cloud.public = True
        with pytest.raises(StorageUnavailableError):
            await p.get("uploads/user/hash.txt")
        cloud.public = False
        await p.delete("uploads/user/hash.txt")
        await p.delete("uploads/user/hash.txt")
        assert not await p.exists("uploads/user/hash.txt")
    finally:
        await p.aclose()


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403, 429, 500, 503])
async def test_provider_failures_are_not_missing_objects_or_secret_messages(status):
    def handle(request):
        return httpx.Response(status, text=KEY, headers={"location": "https://evil.test"})

    p = SupabaseStorageProvider(URL, KEY, "ezo-private", transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(StorageUnavailableError) as error:
            await p.exists("uploads/user/hash.txt")
        assert KEY not in str(error.value) and "evil.test" not in str(error.value)
    finally:
        await p.aclose()


async def test_upload_and_streamed_download_have_hard_byte_limits():
    cloud = CloudFixture()
    p = cloud.provider()
    try:
        with pytest.raises(StorageLimitError):
            await p.put("uploads/user/large", b"x" * 5_000_001)
        assert not cloud.calls
        cloud.objects["uploads/user/large"] = b"x" * 5_000_001
        with pytest.raises(StorageLimitError):
            await p.get("uploads/user/large")
    finally:
        await p.aclose()


@pytest.mark.parametrize(
    "override",
    [
        {"OPENAI_API_KEY": "not-a-live-credential"},
        {"EZO_RATE_LIMIT_CHAT_PER_DAY": 0},
        {"EZO_LEARNING_ENABLED": True},
        {"EZO_OCR_PROVIDER": "auto"},
        {"EZO_OFFICE_CONVERTER": "auto"},
        {"EZO_VOICE_PROVIDERS": "auto"},
        {"EZO_MAX_MESSAGE_CHARS": 4001},
        {"EZO_MAX_UPLOAD_MB": 5},
        {"EZO_STORAGE_PROVIDER": "local"},
    ],
)
def test_production_free_profile_refuses_unsafe_or_unbudgeted_configuration(override):
    settings = free_settings(
        "postgresql://fixture@db.abcdefghijklmnopqrst.supabase.co/db?sslmode=verify-full",
        EZO_ENV="production",
        EZO_CORS_ORIGINS="https://owner.example.test",
        **override,
    )
    with pytest.raises((DeploymentError, ValueError)):
        validate_production(settings)


def test_production_remote_storage_retains_auth_tls_and_budget_checks():
    settings = free_settings(
        "postgresql://fixture@db.abcdefghijklmnopqrst.supabase.co/db?sslmode=verify-full",
        EZO_ENV="production",
        EZO_CORS_ORIGINS="https://owner.example.test",
    )
    validate_production(settings)
    for change in [
        {"database_url": "sqlite:///bad.db"},
        {"auth_mode": "local"},
        {"cors_origins": ["*"]},
    ]:
        with pytest.raises(DeploymentError):
            validate_production(settings.model_copy(update=change))


async def test_office_slot_stays_owned_by_physical_thread_after_http_cancellation():
    import asyncio
    import threading

    from fastapi import HTTPException

    from ezo_api.api.routes.office import _bounded_render

    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def hold():
        started.set()
        try:
            assert release.wait(5)
        finally:
            finished.set()

    task = asyncio.create_task(asyncio.to_thread(_bounded_render, hold))
    try:
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(HTTPException) as error:
            await asyncio.to_thread(_bounded_render, lambda: None)
        assert error.value.status_code == 429
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 3)


async def test_new_storage_secret_is_redacted_by_production_formatter():
    import logging

    from ezo_api.deployment import ProductionFormatter

    settings = free_settings(
        "postgresql://fixture@db.abcdefghijklmnopqrst.supabase.co/db?sslmode=verify-full",
        EZO_ENV="production",
        EZO_CORS_ORIGINS="https://owner.example.test",
    )
    text = ProductionFormatter(settings).format(
        logging.LogRecord("storage", logging.ERROR, __file__, 1, KEY, (), None)
    )
    assert KEY not in text


async def test_corrupt_remote_artifact_is_never_returned_as_a_successful_download():
    from hashlib import sha256

    cloud = CloudFixture()
    p = cloud.provider()
    data = b"original artifact"
    key = "artifacts/user/aa/" + sha256(data).hexdigest() + ".docx"
    try:
        await p.put(key, data)
        cloud.objects[key] = b"truncated or different content"
        with pytest.raises(StorageUnavailableError, match="integrity"):
            await p.get(key)
    finally:
        await p.aclose()


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://ezo_app@db.zyxwvutsrqponmlkjihg.supabase.co/db?sslmode=verify-full",
        "postgresql://ezo_app.zyxwvutsrqponmlkjihg@aws-0-eu.pooler.supabase.com:5432/db?sslmode=verify-full",
        "postgresql://ezo_app@db.example.test/db?sslmode=verify-full",
    ],
)
def test_free_storage_policy_verification_cannot_target_another_database_project(dsn):
    s = free_settings(dsn, EZO_ENV="production", EZO_CORS_ORIGINS="https://owner.example.test")
    with pytest.raises(DeploymentError, match="same Supabase project"):
        validate_production(s)
