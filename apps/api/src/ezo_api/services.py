"""Application service container, built once at startup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ezo_api.agents.registry import AgentRegistry
from ezo_api.auth.local import LocalOwnerAuth
from ezo_api.core.ezo_core import EzoCore
from ezo_api.db.session import Database
from ezo_api.knowledge.embeddings.service import EmbeddingService
from ezo_api.knowledge.fetch import SafeFetcher
from ezo_api.knowledge.ingestion.runner import IngestionRunner
from ezo_api.knowledge.ingestion.service import KnowledgeService
from ezo_api.knowledge.retrieval.retriever import Retriever
from ezo_api.knowledge.vectorstores import VectorStoreResolver
from ezo_api.memory.service import MemoryIndex
from ezo_api.personality.profile import PersonalityProfile, load_personality
from ezo_api.providers.base import ModelProvider
from ezo_api.providers.offline import OfflineProvider
from ezo_api.providers.registry import build_providers
from ezo_api.providers.router import ModelRouter, load_routing_config
from ezo_api.security.rate_limit import SlidingWindowRateLimiter
from ezo_api.settings import Settings
from ezo_api.storage.base import StorageProvider
from ezo_api.storage.local import LocalStorageProvider
from ezo_api.tools.registry import ToolRegistry
from ezo_api.tools.research_tools import KnowledgeSearchTool, WebFetchTool, WebSearchTool
from ezo_api.tools.web_search import WebSearchProvider, build_web_search


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
    storage: StorageProvider
    embeddings: EmbeddingService
    vectors: VectorStoreResolver
    fetcher: SafeFetcher
    knowledge: KnowledgeService
    ingestion: IngestionRunner
    retriever: Retriever
    web_search: WebSearchProvider | None
    tools: ToolRegistry
    memory_index: MemoryIndex


def build_services(
    settings: Settings,
    providers: dict[str, ModelProvider] | None = None,
    web_search: WebSearchProvider | Literal["auto"] | None = "auto",
    fetcher: SafeFetcher | None = None,
) -> Services:
    """Wire everything together. Tests can inject providers, web search and a fetcher."""
    if settings.auth_mode == "token" and settings.api_token is None:
        raise ConfigurationError(
            "EZO_AUTH_MODE=token requires EZO_API_TOKEN to be set in .env (any long random string)."
        )
    token = settings.api_token.get_secret_value() if settings.api_token else None

    routing = load_routing_config(settings.models_config_path)
    personality = load_personality(settings.personality_config_path)
    model_providers = providers if providers is not None else build_providers(settings)
    router = ModelRouter(
        routing,
        model_providers,
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
    db = Database(settings.database_url)
    storage = LocalStorageProvider(settings.storage_dir)
    embeddings = EmbeddingService(routing.embeddings, model_providers)
    vectors = VectorStoreResolver(settings.vector_store)
    safe_fetcher = fetcher or SafeFetcher(settings.fetch_allow_private_networks)
    knowledge = KnowledgeService(
        storage, embeddings, vectors, safe_fetcher, settings.max_upload_bytes
    )
    if web_search == "auto":
        web_search = build_web_search(
            settings.web_search_provider,
            settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else None,
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None,
            settings.web_search_model,
        )
    memory_index = MemoryIndex(embeddings, vectors)
    services = Services(
        settings=settings,
        db=db,
        auth=LocalOwnerAuth(settings.owner_email, settings.owner_name, token),
        router=router,
        personality=personality,
        agents=agents,
        core=core,
        rate_limiter=SlidingWindowRateLimiter(),
        storage=storage,
        embeddings=embeddings,
        vectors=vectors,
        fetcher=safe_fetcher,
        knowledge=knowledge,
        ingestion=IngestionRunner(knowledge, db.sessionmaker, settings.ingestion_mode),
        retriever=Retriever(embeddings, vectors),
        web_search=web_search,
        tools=ToolRegistry([KnowledgeSearchTool(), WebSearchTool(), WebFetchTool()]),
        memory_index=memory_index,
    )
    core.services = services
    core.memory_index = memory_index
    return services
