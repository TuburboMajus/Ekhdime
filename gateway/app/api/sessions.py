from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.errors import ApiError
from app.api.schemas import (
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    CreateConversationRequest,
)
from app.security.auth import require_bearer_token
from app.sessions.repository import ConversationRepository

router = APIRouter(prefix="/conversations", dependencies=[Depends(require_bearer_token)])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(db: AsyncSession = Depends(get_db)):
    conversations = await ConversationRepository(db).list()
    return ConversationListResponse(
        conversations=[
            ConversationSummary.model_validate(c, from_attributes=True) for c in conversations
        ]
    )


@router.post("", response_model=ConversationSummary, status_code=201)
async def create_conversation(
    body: CreateConversationRequest, db: AsyncSession = Depends(get_db)
):
    conversation = await ConversationRepository(db).create(title=body.title)
    return ConversationSummary.model_validate(conversation, from_attributes=True)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    conversation = await ConversationRepository(db).get_with_messages(conversation_id)
    if conversation is None:
        raise ApiError("NOT_FOUND", "Conversation not found.", status_code=404)
    return ConversationDetail.model_validate(conversation, from_attributes=True)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    await ConversationRepository(db).delete(conversation_id)
    return Response(status_code=204)
