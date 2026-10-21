"""Explicit storage selection: remote failures never fall back to a local disk."""

from ezo_api.settings import Settings
from ezo_api.storage.base import StorageProvider
from ezo_api.storage.local import LocalStorageProvider
from ezo_api.storage.supabase import SupabaseStorageProvider


def build_storage(settings: Settings) -> StorageProvider:
    if settings.storage_provider == "supabase":
        return SupabaseStorageProvider(
            settings.supabase_url,
            settings.supabase_storage_key.get_secret_value()
            if settings.supabase_storage_key
            else "",
            settings.supabase_storage_bucket,
            max_bytes=settings.storage_max_bytes,
        )
    return LocalStorageProvider(settings.storage_dir)
