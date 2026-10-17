"""Builds provider adapters from settings. Only providers with a key are enabled."""

from __future__ import annotations

from ezo_api.providers.anthropic_provider import AnthropicProvider
from ezo_api.providers.base import ModelProvider
from ezo_api.providers.gemini_provider import GeminiProvider
from ezo_api.providers.openai_provider import OpenAIProvider
from ezo_api.settings import Settings

KNOWN_PROVIDERS: dict[str, str] = {
    "anthropic": "Anthropic Claude",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
}


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
    return providers
