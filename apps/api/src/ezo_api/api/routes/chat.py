"""Chat endpoints: streaming (Server-Sent Events) and non-streaming."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.api.deps import CurrentUser, ServicesDep, rate_limit
from ezo_api.api.serializers import message_out
from ezo_api.core.ezo_core import (
    CoreActivity,
    CoreDelta,
    CoreDone,
    CoreError,
    CoreEvent,
    CoreMeta,
    PreparedTurn,
    TurnError,
    TurnInput,
)
from ezo_api.db.models import User
from ezo_api.schemas.api import ChatIn, ChatOut
from ezo_api.services import Services

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _validate(body: ChatIn, services: Services) -> TurnInput:
    text = body.message.strip()
    if not text:
        raise HTTPException(422, detail="Message is empty.")
    limit = services.settings.max_message_chars
    if len(text) > limit:
        raise HTTPException(422, detail=f"Message is too long (max {limit} characters).")
    return TurnInput(
        text=text,
        conversation_id=body.conversation_id,
        project_id=body.project_id,
        forced_agent=body.agent,
        channel=body.channel,
    )


async def _prepare(
    services: Services, session: AsyncSession, current: User, turn: TurnInput
) -> PreparedTurn:
    user = await session.get(User, current.id)
    if user is None:
        raise HTTPException(401, detail="User not found.")
    try:
        return await services.core.prepare(session, user, turn)
    except TurnError as exc:
        raise HTTPException(exc.status, detail=exc.message) from exc


def _event_payload(event: CoreEvent) -> dict[str, Any]:
    if isinstance(event, CoreMeta):
        return {
            "conversation_id": str(event.conversation_id),
            "conversation_title": event.conversation_title,
            "created_conversation": event.created_conversation,
            "user_message_id": str(event.user_message_id),
            "run_id": str(event.run_id),
            "intent": event.intent,
            "intent_confidence": event.intent_confidence,
            "agent": event.agent,
            "requested_agent": event.requested_agent,
            "requested_agent_available": event.requested_agent_available,
            "language": event.language,
        }
    if isinstance(event, CoreDelta):
        return {"text": event.text}
    if isinstance(event, CoreActivity):
        return {"stage": event.stage}
    if isinstance(event, CoreDone):
        return {
            "message": message_out(event.message).model_dump(mode="json"),
            "run": {
                "id": str(event.run.id),
                "provider": event.run.provider,
                "model": event.run.model,
                "latency_ms": event.run.latency_ms,
                "input_tokens": event.run.input_tokens,
                "output_tokens": event.run.output_tokens,
            },
        }
    return {
        "code": event.code,
        "message": event.message,
        "hint": event.hint,
        "run_id": str(event.run_id),
        "attempts": event.attempts,
    }


def _sse(event: CoreEvent) -> str:
    data = json.dumps(_event_payload(event), ensure_ascii=False)
    return f"event: {event.type}\ndata: {data}\n\n"


@router.post("/stream", dependencies=[Depends(rate_limit("chat"))])
async def chat_stream(
    body: ChatIn, services: ServicesDep, current: CurrentUser
) -> StreamingResponse:
    """Stream a reply as SSE events: `meta`, many `delta`, then `done` or `error`."""
    turn = _validate(body, services)
    session = services.db.sessionmaker()
    try:
        prepared = await _prepare(services, session, current, turn)
    except BaseException:
        await session.close()
        raise

    async def events() -> AsyncIterator[str]:
        try:
            async for event in services.core.execute(session, prepared):
                yield _sse(event)
        finally:
            await session.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("", dependencies=[Depends(rate_limit("chat"))])
async def chat(body: ChatIn, services: ServicesDep, current: CurrentUser) -> ChatOut:
    """Non-streaming chat: waits for the full reply."""
    turn = _validate(body, services)
    async with services.db.sessionmaker() as session:
        prepared = await _prepare(services, session, current, turn)
        meta: CoreMeta | None = None
        async for event in services.core.execute(session, prepared):
            if isinstance(event, CoreMeta):
                meta = event
            elif isinstance(event, CoreError):
                raise HTTPException(
                    502,
                    detail={
                        "code": event.code,
                        "message": event.message,
                        "hint": event.hint,
                        "run_id": str(event.run_id),
                    },
                )
            elif isinstance(event, CoreDone):
                assert meta is not None
                return ChatOut(
                    conversation_id=meta.conversation_id,
                    message=message_out(event.message),
                    run_id=meta.run_id,
                    agent=meta.agent,
                    requested_agent=meta.requested_agent,
                    intent=meta.intent,
                    language=meta.language,
                )
    raise HTTPException(500, detail="The chat pipeline ended without a reply.")
