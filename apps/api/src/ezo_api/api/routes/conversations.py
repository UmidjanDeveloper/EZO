"""Conversation endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from ezo_api.api.deps import CurrentUser, SessionDep, rate_limit
from ezo_api.api.serializers import message_out
from ezo_api.db.models import Conversation, KnowledgeLibrary, Message, Project
from ezo_api.schemas.api import ConversationOut, ConversationUpdate, MessageOut
from ezo_api.security.audit import audit

router = APIRouter(
    prefix="/api/conversations",
    tags=["conversations"],
    dependencies=[Depends(rate_limit("default"))],
)


async def _owned(
    session: SessionDep, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(404, detail="Conversation not found.")
    return conversation


@router.get("")
async def list_conversations(
    session: SessionDep,
    user: CurrentUser,
    project_id: uuid.UUID | None = None,
    library_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ConversationOut]:
    query = select(Conversation).where(Conversation.user_id == user.id)
    if project_id is not None:
        query = query.where(Conversation.project_id == project_id)
    if library_id is not None:
        query = query.where(Conversation.library_id == library_id)
    query = query.order_by(Conversation.updated_at.desc()).limit(limit)
    rows = (await session.scalars(query)).all()
    return [ConversationOut.model_validate(row) for row in rows]


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> ConversationOut:
    return ConversationOut.model_validate(await _owned(session, user.id, conversation_id))


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[MessageOut]:
    await _owned(session, user.id, conversation_id)
    rows = (
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [message_out(row) for row in reversed(rows)]


@router.patch("/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, session: SessionDep, user: CurrentUser
) -> ConversationOut:
    conversation = await _owned(session, user.id, conversation_id)
    if body.title is not None:
        conversation.title = body.title.strip()
    if "project_id" in body.model_fields_set:
        if body.project_id is not None:
            project = await session.get(Project, body.project_id)
            if project is None or project.user_id != user.id:
                raise HTTPException(404, detail="Project not found.")
        conversation.project_id = body.project_id
    if "library_id" in body.model_fields_set:
        if body.library_id is not None:
            library = await session.get(KnowledgeLibrary, body.library_id)
            if library is None or library.user_id != user.id:
                raise HTTPException(404, detail="Library not found.")
        conversation.library_id = body.library_id
    await session.commit()
    return ConversationOut.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> Response:
    conversation = await _owned(session, user.id, conversation_id)
    audit(
        session,
        user.id,
        "conversation.delete",
        "conversation",
        conversation.id,
        {"title": conversation.title},
    )
    await session.delete(conversation)
    await session.commit()
    return Response(status_code=204)
