from pathlib import Path

from ezo_api.settings import API_DIR, Settings


def make(**env: str) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="sqlite:///x.db", **env)  # type: ignore[call-arg]


def test_blank_storage_dir_uses_default_not_current_folder() -> None:
    assert make(EZO_STORAGE_DIR="").storage_dir == API_DIR / "storage"
    assert make(EZO_STORAGE_DIR="   ").storage_dir == API_DIR / "storage"
    assert make(EZO_STORAGE_DIR="/data/ezo").storage_dir == Path("/data/ezo")


def test_blank_keys_are_none() -> None:
    settings = make(TAVILY_API_KEY="", OPENAI_API_KEY="")
    assert settings.tavily_api_key is None and settings.openai_api_key is None
    assert make(EZO_MAX_UPLOAD_MB="2").max_upload_bytes == 2 * 1024 * 1024
