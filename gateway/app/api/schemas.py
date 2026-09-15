"""Pydantic request/response models mirroring gateway/API.md exactly."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    conversation_id: str | None = None
    include_audio: bool = False


class AgentInfo(BaseModel):
    cli: str
    model: str


class AudioRef(BaseModel):
    available: bool
    url: str
    mime_type: str


class QueryResponse(BaseModel):
    request_id: str
    conversation_id: str
    query: str
    answer: str
    agent: AgentInfo
    audio: AudioRef | None = None
    duration_ms: int
    # The model's chain-of-thought for this turn, kept separate from
    # `answer` on purpose -- clients should render it as a collapsed-by-
    # default "Thinking" section (see mobile/lib/widgets/message_bubble.dart),
    # not mix it into the visible response. None when the CLI/model didn't
    # produce one.
    reasoning: str | None = None


class AudioQueryResponse(BaseModel):
    request_id: str
    conversation_id: str
    transcript: str
    answer: str
    agent: AgentInfo
    audio: AudioRef | None = None
    reasoning: str | None = None


class SttResponse(BaseModel):
    text: str


class TtsRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str | None = None
    format: str = "mp3"
    speed: float = 1.0


class VoicesResponse(BaseModel):
    voices: list[str]
    default: str


class ConversationSummary(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict = Field(default_factory=dict, alias="message_metadata")

    model_config = {"populate_by_name": True, "from_attributes": True}


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class CreateConversationRequest(BaseModel):
    title: str | None = None


class CancelResponse(BaseModel):
    cancelled: bool
