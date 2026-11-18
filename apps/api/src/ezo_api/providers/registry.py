"""Builds provider adapters from settings. Only providers with a key are enabled."""

from __future__ import annotations

from ezo_api.providers.anthropic_provider import AnthropicProvider
from ezo_api.providers.base import ModelProvider
from ezo_api.providers.gemini_provider import GeminiProvider
from ezo_api.providers.limits import CallBudget, LimitedModelProvider
from ezo_api.providers.openai_provider import OpenAIProvider
from ezo_api.settings import Settings

KNOWN_PROVIDERS: dict[str, str] = {
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
}


# Key shapes the providers issue today. A mismatch is a warning, never a refusal: shapes
# can change, and the provider's own answer stays the final word.
_KEY_PREFIXES: dict[str, tuple[str, ...]] = {
    "gemini": ("AIza",),
    "openai": ("sk-",),
    "anthropic": ("sk-ant-",),
}
_DEFAULT_OPENAI_URL = "https://api.openai.com/v1"


def key_warnings(settings: Settings) -> dict[str, str]:
    """Providers whose configured key does not look like one they issue (code per provider).

    Only the prefix is inspected; nothing about the key is returned or logged.
    """
    keys = {
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }
    warnings: dict[str, str] = {}
    for name, secret in keys.items():
        if not secret:
            continue
        if (
            name == "openai"
            and (settings.openai_base_url or _DEFAULT_OPENAI_URL).rstrip("/") != _DEFAULT_OPENAI_URL
        ):
            continue  # an OpenAI-compatible service issues its own key format
        if not secret.get_secret_value().strip().startswith(_KEY_PREFIXES[name]):
            warnings[name] = "unexpected_key_format"
    return warnings


def build_providers(settings: Settings) -> dict[str, ModelProvider]:
    timeout = settings.provider_timeout_seconds
    providers: dict[str, ModelProvider] = {}
    if settings.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(
            settings.anthropic_api_key.get_secret_value(), timeout
        )
    if settings.openai_api_key:
        providers["openai"] = OpenAIProvider(
            settings.openai_api_key.get_secret_value(), timeout, settings.openai_base_url
        )
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(settings.gemini_api_key.get_secret_value(), timeout)
    budget = CallBudget(
        settings.provider_calls_per_day,
        settings.provider_concurrency,
        settings.provider_operation_seconds,
    )
    return {
        name: LimitedModelProvider(provider, budget, settings)
        for name, provider in providers.items()
    }
