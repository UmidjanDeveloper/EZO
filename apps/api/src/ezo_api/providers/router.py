"""Model routing and provider fallback.

The router maps a kind of work (a *route*, e.g. "chat" or "coding") to an
ordered list of (provider, model) candidates from `config/models.toml`, and
streams from the first one that works.
"""

from __future__ import annotations

import logging
import time
import tomllib
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from ezo_api.providers.base import ModelProvider
from ezo_api.providers.errors import ProviderError, ProviderErrorKind
from ezo_api.providers.offline import OFFLINE_MODEL
from ezo_api.providers.types import ChatRequest, Effort, StreamEvent, TextDelta

logger = logging.getLogger(__name__)

DEFAULT_ROUTE = "chat"
_EFFORTS = {"low", "medium", "high"}


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    provider: str
    model: str
    effort: Effort | None = None


@dataclass(frozen=True, slots=True)
class RouteConfig:
    name: str
    description: str
    candidates: tuple[CandidateConfig, ...]


@dataclass(frozen=True, slots=True)
class RoutingConfig:
    routes: Mapping[str, RouteConfig]
    max_output_tokens: int = 16_000
    embeddings: tuple[CandidateConfig, ...] = ()


class RoutingConfigError(ValueError):
    pass


def load_routing_config(path: Path) -> RoutingConfig:
    """Parse and validate `models.toml`. Errors name the file and the problem."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RoutingConfigError(f"Model routing file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RoutingConfigError(f"{path} is not valid TOML: {exc}") from exc
    return parse_routing_config(raw, source=str(path))


def parse_routing_config(raw: dict[str, Any], source: str = "models.toml") -> RoutingConfig:
    routes: dict[str, RouteConfig] = {}
    for name, body in (raw.get("routes") or {}).items():
        candidates: list[CandidateConfig] = []
        for index, item in enumerate(body.get("candidates") or []):
            provider, model = item.get("provider"), item.get("model")
            if not isinstance(provider, str) or not isinstance(model, str):
                raise RoutingConfigError(
                    f"{source}: routes.{name}.candidates[{index}] needs 'provider' and 'model'"
                )
            effort = item.get("effort")
            if effort is not None and effort not in _EFFORTS:
                raise RoutingConfigError(
                    f"{source}: routes.{name}.candidates[{index}].effort must be "
                    f"low, medium or high (got {effort!r})"
                )
            candidates.append(CandidateConfig(provider, model, cast(Effort | None, effort)))
        routes[name] = RouteConfig(name, str(body.get("description", "")), tuple(candidates))
    if DEFAULT_ROUTE not in routes:
        raise RoutingConfigError(f"{source}: a [routes.{DEFAULT_ROUTE}] section is required")
    max_tokens = int((raw.get("defaults") or {}).get("max_output_tokens", 16_000))
    embeddings: list[CandidateConfig] = []
    for index, item in enumerate((raw.get("embeddings") or {}).get("candidates") or []):
        provider, model = item.get("provider"), item.get("model")
        if not isinstance(provider, str) or not isinstance(model, str):
            raise RoutingConfigError(
                f"{source}: embeddings.candidates[{index}] needs 'provider' and 'model'"
            )
        embeddings.append(CandidateConfig(provider, model))
    return RoutingConfig(routes=routes, max_output_tokens=max_tokens, embeddings=tuple(embeddings))


@dataclass(frozen=True, slots=True)
class Candidate:
    provider: ModelProvider
    model: str
    effort: Effort | None = None


@dataclass(slots=True)
class Attempt:
    provider: str
    model: str
    status: str  # ok | failed
    latency_ms: int
    error_kind: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_kind": self.error_kind,
            "error": self.error,
        }


class AllProvidersFailedError(Exception):
    def __init__(self, attempts: list[Attempt]) -> None:
        self.attempts = attempts
        summary = "; ".join(f"{a.provider}/{a.model}: {a.error_kind}" for a in attempts)
        super().__init__(f"All model providers failed ({summary})")


class StreamInterruptedError(Exception):
    """A provider failed after it had already streamed part of the answer."""

    def __init__(self, error: ProviderError) -> None:
        self.error = error
        super().__init__(str(error))


@dataclass(slots=True)
class RoutedStream:
    """Streams one reply, falling back between candidates before the first token."""

    route: str
    candidates: list[Candidate]
    attempts: list[Attempt] = field(default_factory=list)
    selected: Candidate | None = None

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        for candidate in self.candidates:
            started = time.perf_counter()
            produced_text = False
            concrete = replace(request, model=candidate.model, effort=candidate.effort)
            try:
                async for event in candidate.provider.stream_chat(concrete):
                    if isinstance(event, TextDelta):
                        produced_text = True
                    yield event
                self.attempts.append(
                    Attempt(candidate.provider.name, candidate.model, "ok", _ms(started))
                )
                self.selected = candidate
                return
            except Exception as exc:
                error = _as_provider_error(candidate.provider.name, exc)
                logger.warning("Provider %s/%s failed: %s", error.provider, candidate.model, error)
                self.attempts.append(
                    Attempt(
                        candidate.provider.name,
                        candidate.model,
                        "failed",
                        _ms(started),
                        error.kind.value,
                        error.detail[:500],
                    )
                )
                if produced_text:
                    raise StreamInterruptedError(error) from exc
        raise AllProvidersFailedError(self.attempts)


def _as_provider_error(provider: str, exc: Exception) -> ProviderError:
    if isinstance(exc, ProviderError):
        return exc
    logger.exception("Unexpected error from provider %s", provider)
    return ProviderError(provider, ProviderErrorKind.UNKNOWN, f"{type(exc).__name__}: {exc}")


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


class ModelRouter:
    def __init__(
        self,
        config: RoutingConfig,
        providers: Mapping[str, ModelProvider],
        offline: ModelProvider,
        preferred_provider: str | None = None,
    ) -> None:
        self.config = config
        self.providers = dict(providers)
        self.offline = offline
        self.preferred_provider = preferred_provider

    @property
    def is_offline(self) -> bool:
        return not self.providers

    def candidates(self, route: str) -> list[Candidate]:
        """Configured candidates for a route, preferred provider first."""
        if self.is_offline:
            return [Candidate(self.offline, OFFLINE_MODEL)]
        for route_name in (route, DEFAULT_ROUTE):
            route_config = self.config.routes.get(route_name)
            if route_config is None:
                continue
            found = [
                Candidate(self.providers[c.provider], c.model, c.effort)
                for c in route_config.candidates
                if c.provider in self.providers
            ]
            if found:
                if self.preferred_provider:
                    found.sort(key=lambda c: c.provider.name != self.preferred_provider)
                return found
        raise RoutingConfigError(
            "No configured provider appears in models.toml. Add a candidate for one of: "
            + ", ".join(sorted(self.providers))
        )

    def open(self, route: str) -> RoutedStream:
        return RoutedStream(route=route, candidates=self.candidates(route))

    def describe(self) -> dict[str, Any]:
        """Safe summary for the settings screen (no secrets)."""
        routes: dict[str, Any] = {}
        for name, route in self.config.routes.items():
            try:
                active = [
                    {"provider": c.provider.name, "model": c.model, "effort": c.effort}
                    for c in self.candidates(name)
                ]
            except RoutingConfigError:
                active = []
            routes[name] = {"description": route.description, "active_candidates": active}
        return {
            "offline": self.is_offline,
            "preferred_provider": self.preferred_provider,
            "routes": routes,
        }
