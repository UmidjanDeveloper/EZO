"""FastAPI application factory.

Run locally with:  uv run uvicorn ezo_api.main:create_app --factory --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ezo_api import __version__
from ezo_api.api.routes import (
    artifacts,
    chat,
    conversations,
    knowledge,
    language,
    memory,
    official,
    projects,
    stories,
    system,
    voice,
)
from ezo_api.auth.base import AuthError
from ezo_api.providers.base import ModelProvider
from ezo_api.security.rate_limit import RateLimitExceededError
from ezo_api.services import Services, build_services
from ezo_api.settings import Settings, get_settings

logger = logging.getLogger("ezo")


class SecurityHeadersMiddleware:
    """Adds basic security headers. Pure ASGI so streaming responses are untouched."""

    HEADERS = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers.extend(h for h in self.HEADERS if h[0] not in present)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _error(status: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, **extra}}
    )


def create_app(
    settings: Settings | None = None,
    providers: dict[str, ModelProvider] | None = None,
    **overrides: Any,
) -> FastAPI:
    """Build the app. `overrides` (web_search, fetcher, voice, visual) are for tests."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    services: Services = build_services(settings, providers, **overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        mode = (
            "OFFLINE (no AI provider key found)"
            if services.router.is_offline
            else ("providers=" + ",".join(sorted(services.router.providers)))
        )
        logger.info(
            "EZO API %s starting: %s, database=%s",
            __version__,
            mode,
            "sqlite" if settings.is_sqlite else "postgresql",
        )
        async with services.db.sessionmaker() as session:
            interrupted = await services.official.recover_interrupted(session)
        if interrupted:
            logger.info("Marked %s interrupted official-source sync run(s)", interrupted)
        resumed = await services.ingestion.resume_unfinished()
        if resumed:
            logger.info("Resumed ingestion of %s unfinished document(s)", resumed)
        yield
        await services.ingestion.shutdown()
        await services.db.dispose()

    app = FastAPI(
        title="EZO API",
        version=__version__,
        description="EZO — Sen bilan o‘sadigan shaxsiy sun’iy intellekt.",
        lifespan=lifespan,
    )
    app.state.services = services

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        # Lets the web app read download filenames and which voice answered.
        expose_headers=["Content-Disposition", "X-EZO-Voice-Provider"],
    )

    @app.exception_handler(AuthError)
    async def _auth_error(_: Request, exc: AuthError) -> JSONResponse:
        return _error(401, "unauthorized", str(exc))

    @app.exception_handler(RateLimitExceededError)
    async def _rate_limited(_: Request, exc: RateLimitExceededError) -> JSONResponse:
        response = _error(
            429,
            "rate_limited",
            f"Too many requests. Try again in {exc.retry_after_seconds} seconds.",
        )
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
        return _error(exc.status_code, f"http_{exc.status_code}", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", [])[1:]), "message": err.get("msg")}
            for err in exc.errors()
        ]
        return _error(422, "validation_error", "The request is invalid.", details=details)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return _error(500, "internal_error", "Unexpected server error. See the API logs.")

    for module in (
        system,
        chat,
        conversations,
        memory,
        projects,
        knowledge,
        voice,
        artifacts,
        stories,
        language,
        official,
    ):
        app.include_router(module.router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": "EZO API", "version": __version__, "docs": "/docs"}

    return app
