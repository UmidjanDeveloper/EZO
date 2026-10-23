"""Explicit reduced capability boundary; deny new API routes by default."""

import re

from ezo_api.settings import Settings

DISABLED = [
    "native_processing",
    "student_ingestion",
    "knowledge_sync",
    "autonomous_workers",
    "agent_tools",
    "paid_ai",
    "speech",
    "presentations",
    "artifact_mutation_and_deletion",
]
# Full matches, not prefix allowlists. Existing endpoint dependencies still authorize owners.
ROUTES = (
    ("GET", r"/api/(health|status|me)"),
    ("PATCH", r"/api/me/preferences"),
    ("GET|POST", r"/api/(projects|conversations|memories)"),
    ("DELETE", r"/api/memories"),
    ("GET", r"/api/memories/export"),
    ("GET|PATCH|DELETE", r"/api/(projects|conversations|memories)/[a-fA-F0-9-]{36}"),
    ("GET", r"/api/conversations/[a-fA-F0-9-]{36}/messages"),
    ("POST", r"/api/chat(/stream)?"),
    ("GET", r"/api/personal/(profile|goals|memories/export)"),
    ("POST", r"/api/personal/(goals|consent)"),
    ("PATCH|DELETE", r"/api/personal/goals/[a-fA-F0-9-]{36}"),
    ("GET", r"/api/ielts/(cue-cards|voice-status|history|stats)"),
    ("POST", r"/api/ielts/sessions"),
    ("GET", r"/api/ielts/sessions/[a-fA-F0-9-]{36}"),
    ("POST", r"/api/ielts/sessions/[a-fA-F0-9-]{36}/advance"),
    ("GET", r"/api/office/(templates|artifacts)"),
    ("POST", r"/api/office/(documents|spreadsheets)"),
    ("GET", r"/api/artifacts"),
    (
        "GET",
        r"/api/artifacts/[a-fA-F0-9-]{36}(/(download|versions|exports/[a-z]+|versions/[0-9]+/(download|text|exports/[a-z0-9-]+)))?",
    ),
)


def allowed(method: str, path: str) -> bool:
    return any(
        re.fullmatch(verbs, method) and re.fullmatch(pattern, path) for verbs, pattern in ROUTES
    )


def validate_free_beta(settings: Settings) -> None:
    if settings.deployment_profile != "free-beta":
        return
    token = settings.api_token.get_secret_value().strip() if settings.api_token else ""
    if settings.auth_mode != "token" or len(token) < 32 or settings.storage_provider != "supabase":
        raise ValueError("Free beta requires owner token auth and private remote storage.")
    if settings.environment == "development":
        raise ValueError("Hosted free beta requires EZO_ENV=production; test is for fixtures only.")
    if settings.elevenlabs_api_key:
        raise ValueError("Free beta requires absent ElevenLabs credentials.")
    if any(
        value and value.get_secret_value().strip()
        for value in (
            settings.openai_api_key,
            settings.anthropic_api_key,
            settings.gemini_api_key,
            settings.tavily_api_key,
            settings.voicestudio_api_key,
            settings.github_token,
        )
    ):
        raise ValueError("Free beta forbids AI, search, voice and GitHub credentials.")
    if (
        settings.learning_enabled
        or settings.ruflo_enabled
        or settings.expose_debug_traces
        or settings.ocr_provider != "none"
        or settings.office_converter != "none"
        or settings.web_search_provider != "none"
        or settings.scholar_provider != "none"
        or settings.voice_providers != ["none"]
        or settings.image_providers != ["none"]
        or settings.voicestudio_url
        or settings.max_upload_bytes > 5_000_000
        or settings.max_message_chars > 4_000
        or not 0 < settings.rate_limit_chat_per_minute <= 5
        or not 0 < settings.rate_limit_chat_per_day <= 10
        or not 0 < settings.rate_limit_default_per_minute <= 60
    ):
        raise ValueError(
            "Free beta requires disabled providers/workers and conservative positive limits."
        )
