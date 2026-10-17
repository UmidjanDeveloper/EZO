"""Application service container, built once at startup."""

from __future__ import annotations

from dataclasses import dataclass

from ezo_api.agents.registry import AgentRegistry
from ezo_api.auth.local import LocalOwnerAuth
from ezo_api.core.ezo_core import EzoCore
from ezo_api.db.session import Database
from ezo_api.personality.profile import PersonalityProfile, load_personality
from ezo_api.providers.base import ModelProvider
from ezo_api.providers.offline import OfflineProvider
from ezo_api.providers.registry import build_providers
from ezo_api.providers.router import ModelRouter, load_routing_config
from ezo_api.security.rate_limit import SlidingWindowRateLimiter
from ezo_api.settings import Settings


class ConfigurationError(RuntimeError):
    """Startup configuration problem with a human-readable explanation."""


@dataclass(slots=True)
class Services:
    settings: Settings
    db: Database
    auth: LocalOwnerAuth
    router: ModelRouter
    personality: PersonalityProfile
    agents: AgentRegistry
    core: EzoCore
    rate_limiter: SlidingWindowRateLimiter


def build_services(
    settings: Settings, providers: dict[str, ModelProvider] | None = None
) -> Services:
    """Wire everything together. `providers` lets tests inject fake providers."""
    if settings.auth_mode == "token" and settings.api_token is None:
        raise ConfigurationError(
            "EZO_AUTH_MODE=token requires EZO_API_TOKEN to be set in .env (any long random string)."
        )
    token = settings.api_token.get_secret_value() if settings.api_token else None

    routing = load_routing_config(settings.models_config_path)
    personality = load_personality(settings.personality_config_path)
    router = ModelRouter(
        routing,
        providers if providers is not None else build_providers(settings),
        OfflineProvider(chunk_delay_seconds=0.02 if settings.environment != "test" else 0.0),
        preferred_provider=settings.preferred_provider,
    )
    agents = AgentRegistry()
    core = EzoCore(
        router=router,
        agents=agents,
        personality=personality,
        timezone=settings.timezone,
        context_message_limit=settings.context_message_limit,
        context_char_budget=settings.context_char_budget,
        max_output_tokens=routing.max_output_tokens,
    )
    return Services(
        settings=settings,
        db=Database(settings.database_url),
        auth=LocalOwnerAuth(settings.owner_email, settings.owner_name, token),
        router=router,
        personality=personality,
        agents=agents,
        core=core,
        rate_limiter=SlidingWindowRateLimiter(),
    )
