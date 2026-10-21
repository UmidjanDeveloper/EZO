"""Offline provider: used only when no real AI provider is configured.

It is NOT an AI model. It answers with a clear notice, in the user's language,
explaining how to connect a provider, so the full stack can be run and tested
without API keys.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from ezo_api.providers.base import ModelProvider
from ezo_api.providers.types import (
    Capability,
    ChatRequest,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)

OFFLINE_MODEL = "offline-notice"

_NOTICE = {
    "uz": (
        "⚠️ EZO hozir **oflayn rejimda**: hech qanday AI provayder ulanmagan, shuning uchun "
        "bu javob sun'iy intellektdan emas.\n\n"
        "Ulash uchun loyiha ildizidagi `.env` fayliga `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` "
        "yoki `GEMINI_API_KEY` dan birini yozing va EZO'ni qayta ishga tushiring."
    ),
    "en": (
        "⚠️ EZO is running in **offline mode**: no AI provider is connected, so this reply "
        "does not come from an AI model.\n\n"
        "To connect one, put `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY` in the "
        "`.env` file in the project root and restart EZO."
    ),
    "ru": (
        "⚠️ EZO работает в **офлайн-режиме**: ни один AI-провайдер не подключён, поэтому "
        "этот ответ не от модели ИИ.\n\n"
        "Чтобы подключить, укажите `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` или `GEMINI_API_KEY` "
        "в файле `.env` в корне проекта и перезапустите EZO."
    ),
}


class OfflineProvider(ModelProvider):
    name = "offline"
    display_name = "Offline (no AI provider)"
    capabilities = frozenset({Capability.CHAT, Capability.STREAMING})

    def __init__(self, chunk_delay_seconds: float = 0.0, *, free_beta: bool = False) -> None:
        self._delay = chunk_delay_seconds
        self._free_beta = free_beta

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        language = request.hints.get("language", "uz")
        template = _NOTICE.get(language, _NOTICE["uz"])
        if self._free_beta:
            template = {
                "uz": (
                    "EZO bepul beta: AI ulanmagan. Bu AI javobi emas. Suhbat saqlanadi; "
                    "manual xotira, loyihalar, maqsadlar, matnli IELTS mashqi "
                    "va kichik Office eksportlari mavjud."
                ),
                "en": (
                    "EZO free beta: no AI is connected. This is not an AI answer. "
                    "Chat is saved; manual memory, projects, goals, IELTS text practice "
                    "and lightweight Office exports are available."
                ),
                "ru": (
                    "EZO бесплатная бета: ИИ не подключён. Это не ответ ИИ. Доступны "
                    "история чата, ручная память, проекты, цели, текстовая практика IELTS "
                    "и небольшие документы Office."
                ),
            }.get(language, "EZO free beta: no AI is connected. This is not an AI answer.")
        for word in template.split(" "):
            if self._delay:
                await asyncio.sleep(self._delay)
            yield TextDelta(word + " ")
        yield StreamEnd(model=OFFLINE_MODEL, usage=Usage(), finish_reason="offline")
