"""Thread/message persistence with per-user ownership enforcement.

Every function takes the caller's user id; unknown threads raise 404 and
other users' threads raise 403, so routes cannot forget the check.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ChatMessage, ChatThread

# created_at has microsecond precision. Both rows of a turn commit in one
# transaction, so Postgres now() would give them the same timestamp; the
# explicit nudge keeps the user message strictly before its reply.
_TURN_OFFSET = timedelta(microseconds=1)


async def create_thread(
    session: AsyncSession, user_id: UUID, title: str | None = None
) -> ChatThread:
    thread = ChatThread(user_id=user_id, title=title)
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return thread


async def list_threads(session: AsyncSession, user_id: UUID) -> list[ChatThread]:
    result = await session.execute(
        select(ChatThread)
        .where(ChatThread.user_id == user_id)
        .order_by(ChatThread.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_owned_thread(
    session: AsyncSession, user_id: UUID, thread_id: UUID
) -> ChatThread:
    thread = await session.get(ChatThread, thread_id)
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Thread not found")
    if thread.user_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your thread")
    return thread


async def list_messages(session: AsyncSession, thread_id: UUID) -> list[ChatMessage]:
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def persist_turn(
    session: AsyncSession,
    thread: ChatThread,
    user_message: ChatMessage,
    assistant_message: ChatMessage,
) -> None:
    """Insert both messages and bump the thread in one transaction.

    Called only after the assistant stream completed, so a failed or
    interrupted turn persists nothing.
    """
    now = datetime.now(UTC)
    user_message.created_at = now
    assistant_message.created_at = now + _TURN_OFFSET
    thread.updated_at = now
    session.add_all([user_message, assistant_message])
    await session.commit()
