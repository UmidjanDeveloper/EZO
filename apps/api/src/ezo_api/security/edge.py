"""The API's front door: authenticate and size-check a request before anything reads it.

FastAPI reads a request body (JSON into memory, multipart onto disk) before route
dependencies such as the token check run. Without this middleware anyone who knows the
API address could send gigabytes and exhaust the server without a token. So, for every
`/api/` request except the public health probe:

1. token mode: the `Authorization: Bearer` token is checked first (constant time). A
   wrong or missing token gets 401 without the body being read. Failed attempts share one
   small global budget (no client IP is trusted, so a spoofed header cannot evade it, and
   the owner, who passes the check, is never slowed down by it);
2. a declared `Content-Length` above the limit gets 413 at once; a body without a
   declared length (chunked) is counted while it arrives and refused past the limit.

Authenticated requests are marked in the ASGI scope, so the per-route rate limits count
the owner's own requests, not an attacker's.

3. local mode (no token, never allowed in production): a state-changing request that a
   browser sends from another site carries an ``Origin`` header. Unless that origin is
   one of the configured CORS origins it is refused (403) before any route runs, so a
   web page cannot make the owner's browser queue uploads or change data (finding F23;
   CORS alone does not stop "simple" cross-site POSTs, it only hides the response).
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ezo_api.security.rate_limit import RateLimitExceededError, SlidingWindowRateLimiter

PUBLIC_PATHS = frozenset({"/api/health"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
AUTHENTICATED = "ezo.authenticated"
PRINCIPAL = "ezo.principal"
"""Rate-limit key of the authenticated caller: "owner" or "user:<id>" for a per-user token."""
FAILED_AUTH_PER_MINUTE = 30


class BodyTooLargeError(HTTPException):
    """Raised while a body without a declared length grows past the limit. An
    HTTPException, so FastAPI's body reader passes it on as 413 instead of a parse error."""

    def __init__(self) -> None:
        super().__init__(413, detail={"code": "too_large", "message": "The request is too large."})


async def _reply(send: Send, status: int, code: str, message: str, **headers: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    raw = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    raw.extend((k.lower().encode(), v.encode()) for k, v in headers.items())
    await send({"type": "http.response.start", "status": status, "headers": raw})
    await send({"type": "http.response.body", "body": body})


class EdgeGuardMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        token: str | None,
        max_body_bytes: int,
        free_beta: bool = False,
        allowed_origins: list[str] | None = None,
        token_validator: Callable[[str], Awaitable[str | None]] | None = None,
    ) -> None:
        self.app = app
        self.allowed_origins = frozenset(o.rstrip("/") for o in allowed_origins or [])
        # Owner-issued per-user tokens are checked against the database (hash lookup)
        # before any body is read, exactly like the installation token.
        self.token_validator = token_validator
        self.token = token.encode() if token else None
        self.max_body = max_body_bytes
        self.free_beta = free_beta
        self.failures = SlidingWindowRateLimiter()

    async def _principal(self, scope: Scope) -> str | None:
        """Who is calling ("owner" or "user:<id>"), or None when not authorized."""
        if self.token is None:
            return "owner"
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                scheme, _, given = value.decode("latin-1").partition(" ")
                if scheme.lower() != "bearer":
                    return None
                if hmac.compare_digest(given.strip().encode("latin-1"), self.token):
                    return "owner"
                if self.token_validator is None:
                    return None
                return await self.token_validator(given.strip())
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not path.startswith("/api/") or path in PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)  # CORS preflight carries no token or body
            return

        if self.token is None and scope.get("method") not in SAFE_METHODS:
            origin = next(
                (v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"origin"),
                None,
            )
            if origin is not None and origin.rstrip("/") not in self.allowed_origins:
                await _reply(send, 403, "cross_site", "Cross-site requests are not allowed.")
                return

        try:
            principal = await self._principal(scope)
        except Exception:  # the token store is unreachable: fail closed, readable reply
            await _reply(send, 503, "unavailable", "Authentication is temporarily unavailable.")
            return
        if principal is None:
            try:
                self.failures.check("failed-auth", FAILED_AUTH_PER_MINUTE)
            except RateLimitExceededError as exc:
                await _reply(
                    send,
                    429,
                    "rate_limited",
                    f"Too many requests. Try again in {exc.retry_after_seconds} seconds.",
                    **{"Retry-After": str(exc.retry_after_seconds)},
                )
                return
            await _reply(send, 401, "unauthorized", "Missing or invalid API token.")
            return
        state = scope.setdefault("state", {})
        state[AUTHENTICATED] = self.token is not None
        state[PRINCIPAL] = principal

        if self.free_beta:
            from ezo_api.free_beta import allowed

            if not allowed(scope.get("method", ""), path):
                await _reply(
                    send,
                    409,
                    "feature_disabled",
                    "This capability is disabled in the free beta profile.",
                )
                return

        declared = None
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    await _reply(send, 400, "bad_request", "Invalid Content-Length.")
                    return
        if declared is not None and declared > self.max_body:
            await _reply(send, 413, "too_large", "The request is too large.")
            return

        received = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise BodyTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except BodyTooLargeError:
            if not started:
                await _reply(send, 413, "too_large", "The request is too large.")
