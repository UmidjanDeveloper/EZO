"""Provider error types with beginner-readable messages."""

from __future__ import annotations

from enum import StrEnum


class ProviderErrorKind(StrEnum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MODEL_NOT_FOUND = "model_not_found"
    BAD_REQUEST = "bad_request"
    UNKNOWN = "unknown"


_HINTS: dict[ProviderErrorKind, str] = {
    ProviderErrorKind.AUTH: "The API key was rejected. Check the key in your .env file.",
    ProviderErrorKind.RATE_LIMIT: "The provider is rate limiting requests or the account "
    "has no remaining credit. Wait a moment or check billing.",
    ProviderErrorKind.UNAVAILABLE: "Could not reach the provider (network problem or outage).",
    ProviderErrorKind.TIMEOUT: "The provider took too long to answer.",
    ProviderErrorKind.MODEL_NOT_FOUND: "The model name is not available for this API key. "
    "Check apps/api/config/models.toml.",
    ProviderErrorKind.BAD_REQUEST: "The provider rejected the request.",
    ProviderErrorKind.UNKNOWN: "Unexpected provider error.",
}


class ProviderError(Exception):
    """A failure talking to a model provider."""

    def __init__(
        self, provider: str, kind: ProviderErrorKind, detail: str, status: int | None = None
    ) -> None:
        self.provider = provider
        self.kind = kind
        self.detail = detail
        self.status = status
        super().__init__(f"[{provider}] {kind.value}: {detail}")

    @property
    def hint(self) -> str:
        return _HINTS[self.kind]


def kind_from_status(status: int | None) -> ProviderErrorKind:
    if status in (401, 403):
        return ProviderErrorKind.AUTH
    if status == 404:
        return ProviderErrorKind.MODEL_NOT_FOUND
    if status == 429:
        return ProviderErrorKind.RATE_LIMIT
    if status in (408, 504):
        return ProviderErrorKind.TIMEOUT
    if status is not None and status >= 500:
        return ProviderErrorKind.UNAVAILABLE
    if status is not None and 400 <= status < 500:
        return ProviderErrorKind.BAD_REQUEST
    return ProviderErrorKind.UNKNOWN


class CapabilityNotAvailableError(Exception):
    """Raised when a capability is not implemented yet for an adapter."""

    def __init__(self, provider: str, capability: str, milestone: str) -> None:
        self.provider = provider
        self.capability = capability
        self.milestone = milestone
        super().__init__(
            f"'{capability}' is not available yet for provider '{provider}' "
            f"(planned for {milestone})."
        )
