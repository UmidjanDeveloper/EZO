"""Owner scope checks shared by direct authoring/session entry points."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ezo_api.db.models import Conversation


async def require_owned_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID | None
) -> None:
    if (
        conversation_id is not None
        and await session.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )
        is None
    ):
        raise HTTPException(404, detail="Conversation not found.")
