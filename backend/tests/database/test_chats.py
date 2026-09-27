"""Unit tests for chats.py persistence helpers. Mocked session, no DB."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.database import chats
from app.database.models import ChatMessage, ChatThread, MessageRole


class FakeSession:
    """Minimal AsyncSession stand-in: get/execute/refresh + tracked adds."""

    def __init__(self, thread: ChatThread | None = None) -> None:
        self._thread = thread
        self.added: list = []
        self.commit_count = 0

    async def get(self, model, key):
        assert model is ChatThread
        return self._thread

    async def execute(self, stmt):
        rows = [self._thread] if self._thread else []

        class Scalars:
            def all(self):
                return list(rows)

        class Result:
            def scalars(self):
                return Scalars()

        return Result()

    def add(self, obj) -> None:
        self.added.append(obj)

    def add_all(self, objs) -> None:
        self.added.extend(objs)

    async def commit(self) -> None:
        self.commit_count += 1

    async def refresh(self, obj) -> None:
        pass


def _thread(user_id=None) -> ChatThread:
    return ChatThread(id=uuid4(), user_id=user_id or uuid4(), title="t")


async def test_create_thread_commits() -> None:
    session = FakeSession()
    thread = await chats.create_thread(session, uuid4(), "My thread")
    assert session.added == [thread]
    assert session.commit_count == 1
    assert thread.title == "My thread"


async def test_list_threads_scoped_to_user() -> None:
    user_id = uuid4()
    thread = _thread(user_id)
    session = FakeSession(thread)
    # execute() returns only the thread the (mocked) query yields; the real
    # scoping happens in SQL. Here we assert wiring, not SQL semantics.
    assert await chats.list_threads(session, user_id) == [thread]


async def test_get_owned_thread_happy_path() -> None:
    user_id = uuid4()
    thread = _thread(user_id)
    assert await chats.get_owned_thread(FakeSession(thread), user_id, thread.id) is thread


async def test_get_owned_thread_unknown_is_404() -> None:
    with pytest.raises(HTTPException) as excinfo:
        await chats.get_owned_thread(FakeSession(None), uuid4(), uuid4())
    assert excinfo.value.status_code == 404


async def test_get_owned_thread_foreign_is_403() -> None:
    thread = _thread()  # owned by someone else
    with pytest.raises(HTTPException) as excinfo:
        await chats.get_owned_thread(FakeSession(thread), uuid4(), thread.id)
    assert excinfo.value.status_code == 403


async def test_persist_turn_one_commit_and_offsets_timestamps() -> None:
    session = FakeSession()
    thread = _thread()
    user_message = ChatMessage(
        thread_id=thread.id, role=MessageRole.USER, content="q"
    )
    assistant_message = ChatMessage(
        thread_id=thread.id, role=MessageRole.ASSISTANT, content="a"
    )
    await chats.persist_turn(session, thread, user_message, assistant_message)
    assert session.commit_count == 1
    assert session.added == [user_message, assistant_message]
    assert assistant_message.created_at > user_message.created_at
    assert thread.updated_at is not None
