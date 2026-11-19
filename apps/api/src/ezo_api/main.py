"""FastAPI application factory.

Run locally with:  uv run uvicorn ezo_api.main:create_app --factory --reload
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ezo_api import __version__
from ezo_api.api.routes import (
    academic,
    accounts,
    artifacts,
    career,
    chancery,
    chat,
    conversations,
    district,
    document_jobs,
    governance,
    ielts,
    improvements,
    jarvis,
    knowledge,
    language,
    learning,
    memory,
    office,
    official,
    personal,
    presentations,
    projects,
    refresh,
    schedule,
    skills,
    stories,
    student,
    student_paths,
    student_study,
    system,
    translation,
    vision,
    voice,
    writing,
)
from ezo_api.auth.base import AuthError
from ezo_api.deployment import configure_production_logging, validate_production
from ezo_api.providers.base import ModelProvider
from ezo_api.security.edge import EdgeGuardMiddleware
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


def _user_token_validator(services: Services) -> Callable[[str], Awaitable[str | None]]:
    """Edge check for owner-issued per-user tokens (hash lookup, no body read).

    Returns the rate-limit key of the token's user, or None when the token is invalid."""
    from ezo_api.auth.local import user_for_token

    async def validate(token: str) -> str | None:
        async with services.db.sessionmaker() as session:
            user = await user_for_token(session, token)
            return None if user is None else f"user:{user.id}"

    return validate


async def _telegram_poller(services: Services) -> None:
    """Read EZO's bot messages in the background: employees' progress reports and /start
    links. Stops for good when Telegram says another reader (a webhook) owns the bot."""
    from ezo_api.district.telegram_reports import poll_once
    from ezo_api.jarvis.telegram import TelegramClient, TelegramError

    token = services.settings.telegram_bot_token
    if token is None:
        return
    client = TelegramClient(token.get_secret_value())
    while True:
        try:
            async with services.db.sessionmaker() as session:
                stored, handled = await poll_once(session, client)
                await session.commit()
            if stored or handled:
                logger.info("Telegram: %s new message(s), %s report(s) handled", stored, handled)
        except asyncio.CancelledError:
            raise
        except TelegramError as exc:
            if "webhook" in exc.message.lower() or "conflict" in exc.message.lower():
                logger.warning("Telegram polling stopped: %s", exc.message)
                return
            logger.warning("Telegram polling failed: %s", exc.message)
        except Exception:
            logger.exception("Telegram polling failed")
        await asyncio.sleep(services.settings.telegram_poll_seconds)


async def _scheduler(services: Services) -> None:
    """Jadval: run due jobs every `EZO_SCHEDULER_SECONDS`. Each job is claimed with a lease,
    so a second API process never runs the same job at the same time."""
    from ezo_api.schedule.service import tick

    while True:
        try:
            ran = await tick(services)
            if ran:
                logger.info("Scheduler: ran %s job(s)", ran)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(services.settings.scheduler_seconds)


def create_app(
    settings: Settings | None = None,
    providers: dict[str, ModelProvider] | None = None,
    **overrides: Any,
) -> FastAPI:
    """Build the app. `overrides` (web_search, fetcher, voice, visual) are for tests."""
    settings = settings or get_settings()
    from ezo_api.free_beta import validate_free_beta

    validate_free_beta(settings)
    from ezo_api.deployment import check_environment

    check_environment(settings, os.environ)
    validate_production(settings)
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    configure_production_logging(settings)
    services: Services = build_services(settings, providers, **overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            from ezo_api.deployment import check_database

            await asyncio.to_thread(check_database, settings)
            from ezo_api.storage.supabase import SupabaseStorageProvider

            if isinstance(services.storage, SupabaseStorageProvider):
                await services.storage.check_private()
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
            from ezo_api.providers.registry import key_warnings

            for name in key_warnings(settings):
                logger.warning(
                    "The %s API key does not look like a key %s issues; requests will likely be "
                    "rejected. Check it in .env (see docs/master/EZO_OWNER_TEST_UZ.md).",
                    name,
                    name,
                )
            if settings.deployment_profile != "free-beta":
                async with services.db.sessionmaker() as session:
                    interrupted = await services.official.recover_interrupted(session)
                if interrupted:
                    logger.info("Marked %s interrupted official-source sync run(s)", interrupted)
                resumed = await services.ingestion.resume_unfinished()
                if resumed:
                    logger.info("Resumed ingestion of %s unfinished document(s)", resumed)
                if services.learning is not None:
                    relearn = await services.learning.resume_unfinished()
                    if relearn:
                        logger.info("Resumed reading of %s learned source(s)", relearn)
            poller = (
                asyncio.create_task(_telegram_poller(services))
                if settings.telegram_bot_token
                and settings.telegram_poll_seconds > 0
                and settings.environment != "test"
                else None
            )
            scheduler = (
                asyncio.create_task(_scheduler(services))
                if settings.scheduler_seconds > 0
                and settings.environment != "test"
                and settings.deployment_profile != "free-beta"
                else None
            )
            yield
        finally:
            if "poller" in locals() and poller is not None:
                poller.cancel()
            if "scheduler" in locals() and scheduler is not None:
                scheduler.cancel()
            if services.learning is not None:
                await services.learning.shutdown()
            await services.ingestion.shutdown()
            await services.storage.aclose()
            await services.db.dispose()

    app = FastAPI(
        title="EZO API",
        version=__version__,
        description="EZO — Sen bilan o‘sadigan shaxsiy sun’iy intellekt.",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None if settings.environment == "production" else "/redoc",
        openapi_url=None if settings.environment == "production" else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.services = services

    # Innermost: token and size checks before any route reads the body. CORS stays
    # outermost so the browser can read 401/413 answers.
    app.add_middleware(
        EdgeGuardMiddleware,
        token=services.auth.required_token,
        max_body_bytes=262_144
        if settings.deployment_profile == "free-beta"
        else settings.max_upload_bytes + 2 * 1024 * 1024,
        free_beta=settings.deployment_profile == "free-beta",
        allowed_origins=settings.cors_origins,
        token_validator=_user_token_validator(services),
    )
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

    from ezo_api.storage.base import StorageError
    from ezo_api.storage.supabase import StorageLimitError

    @app.exception_handler(StorageError)
    async def _storage_error(_: Request, exc: StorageError) -> JSONResponse:
        return _error(
            413 if isinstance(exc, StorageLimitError) else 503,
            "storage_unavailable",
            "Private storage could not complete the request.",
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
        refresh,
        document_jobs,
        governance,
        improvements,
        jarvis,
        student,
        student_study,
        student_paths,
        knowledge,
        voice,
        vision,
        artifacts,
        stories,
        language,
        ielts,
        official,
        personal,
        presentations,
        office,
        writing,
        translation,
        academic,
        career,
        learning,
        accounts,
        district,
        chancery,
        skills,
        schedule,
    ):
        app.include_router(module.router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": "EZO API", "version": __version__, "docs": "/docs"}

    return app
