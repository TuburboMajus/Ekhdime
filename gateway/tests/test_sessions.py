from sqlalchemy import select

from app.sessions.models import Message
from app.sessions.repository import ConversationRepository


async def test_create_and_get_conversation(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create(title="Sprint planning")
    fetched = await repo.get(conversation.id)
    assert fetched is not None
    assert fetched.title == "Sprint planning"


async def test_get_or_create_returns_existing(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create()
    same = await repo.get_or_create(conversation.id)
    assert same.id == conversation.id


async def test_get_or_create_creates_when_missing_or_none(db_session):
    repo = ConversationRepository(db_session)
    created_from_none = await repo.get_or_create(None)
    created_from_unknown = await repo.get_or_create("does-not-exist")
    assert created_from_none.id != created_from_unknown.id


async def test_list_orders_by_most_recently_active(db_session):
    repo = ConversationRepository(db_session)
    first = await repo.create(title="first")
    second = await repo.create(title="second")
    # Touch `first` after `second` was created -- it should now sort first.
    await repo.add_message(first.id, "user", "hello again")

    conversations = await repo.list()
    assert conversations[0].id == first.id
    assert conversations[1].id == second.id


async def test_delete_conversation_cascades_messages(db_session):
    # Regression test: this used to only check the conversation row was
    # gone, not the messages -- which missed a real bug where SQLite's
    # ondelete="CASCADE" was never enforced (see repository.py's
    # init_engine) and deleted conversations left orphaned message rows
    # behind forever.
    repo = ConversationRepository(db_session)
    conversation = await repo.create()
    await repo.add_message(conversation.id, "user", "hi")

    await repo.delete(conversation.id)
    assert await repo.get(conversation.id) is None

    result = await db_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    assert result.scalars().all() == []


async def test_recent_messages_respects_limit_and_order(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create()
    for i in range(5):
        await repo.add_message(conversation.id, "user", f"message {i}")

    recent = await repo.recent_messages(conversation.id, limit=2)
    assert [m.content for m in recent] == ["message 3", "message 4"]


async def test_get_with_messages_eager_loads(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create()
    await repo.add_message(conversation.id, "user", "hi")
    await repo.add_message(conversation.id, "assistant", "hello")

    fetched = await repo.get_with_messages(conversation.id)
    # Accessing `.messages` must not require any further await/IO -- this
    # is what the API layer relies on (see app/api/sessions.py).
    assert [m.content for m in fetched.messages] == ["hi", "hello"]


async def test_add_message_stores_metadata(db_session):
    repo = ConversationRepository(db_session)
    conversation = await repo.create()
    message = await repo.add_message(
        conversation.id, "assistant", "ABC-42.", metadata={"tools_used": ["plane.list_issues"]}
    )
    assert message.message_metadata == {"tools_used": ["plane.list_issues"]}
