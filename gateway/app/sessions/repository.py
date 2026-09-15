"""Async CRUD for conversations/messages, plus the bounded context window
used when building a prompt (`CONVERSATION_CONTEXT_MESSAGES`)."""

from __future__ import annotations

from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.sessions.models import Base, Conversation, Message, _now

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str) -> AsyncEngine:
    global _engine, _sessionmaker
    _engine = create_async_engine(database_url, future=True)

    if _engine.sync_engine.dialect.name == "sqlite":
        # SQLite ignores FOREIGN KEY constraints (including Message's
        # `ondelete="CASCADE"` -- see models.py) unless each connection
        # explicitly turns enforcement on. Without this, deleting a
        # conversation silently orphans its messages instead of cascading
        # -- found live: DELETE /conversations/{id} left `messages` rows
        # behind pointing at a conversation_id that no longer existed.
        @event.listens_for(_engine.sync_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def create_all() -> None:
    assert _engine is not None, "call init_engine() first"
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def session() -> AsyncSession:
    assert _sessionmaker is not None, "call init_engine() first"
    return _sessionmaker()


class ConversationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, title: str | None = None) -> Conversation:
        conversation = Conversation(title=title)
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def get_with_messages(self, conversation_id: str) -> Conversation | None:
        """Like `get()`, but eagerly loads `.messages`.

        Needed anywhere the result crosses out of the async session context
        before `.messages` is accessed (e.g. Pydantic's `model_validate`
        building the `GET /conversations/{id}` response) -- SQLAlchemy's
        default lazy-load requires an active greenlet and raises
        `MissingGreenlet` otherwise.
        """
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def list(self) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation).order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, conversation_id: str) -> None:
        await self.db.execute(delete(Conversation).where(Conversation.id == conversation_id))
        await self.db.commit()

    async def get_or_create(self, conversation_id: str | None) -> Conversation:
        if conversation_id:
            existing = await self.get(conversation_id)
            if existing:
                return existing
        return await self.create()

    async def recent_messages(self, conversation_id: str, limit: int) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
        )
        self.db.add(message)
        conversation = await self.get(conversation_id)
        if conversation is not None:
            # Explicitly touch updated_at so `list()` orders by
            # most-recently-active; SQLAlchemy's onupdate= only fires when a
            # column is actually flagged dirty, which merely re-adding an
            # unchanged object to the session does not do.
            conversation.updated_at = _now()
        await self.db.commit()
        await self.db.refresh(message)
        return message
