"""ORM -> API schema conversion helpers."""

from __future__ import annotations

from ezo_api.db.models import Message, User
from ezo_api.schemas.api import MessageOut, Preferences, UserOut


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        language=message.language,
        agent=message.agent,
        agent_run_id=message.agent_run_id,
        metadata=message.meta or {},
        created_at=message.created_at,
    )


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        preferences=Preferences.model_validate(user.preferences or {}),
    )
