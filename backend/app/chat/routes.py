"""Chat REST + streaming routes.

Stream wire format: AI SDK UI message stream v1 (SSE) — `start`, `start-step`,
`text-start`/`text-delta`/`text-end`, `finish-step`, `finish`, `[DONE]` —
which `useChat` + `DefaultChatTransport` consume directly.
"""

import asyncio
import json
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.auth import CurrentUser, GetSession, get_current_user
from app.chat import messages as messages_lib
from app.database import chats
from app.database.models import ChatMessage, MessageRole

router = APIRouter(tags=["chat"])


class ThreadCreate(BaseModel):
    title: str | None = None


class ThreadOut(BaseModel):
    id: UUID
    title: str | None
    created_at: str
    updated_at: str


def _thread_out(thread: Any) -> ThreadOut:
    return ThreadOut(
        id=thread.id,
        title=thread.title,
        created_at=thread.created_at.isoformat(),
        updated_at=thread.updated_at.isoformat(),
    )


@router.get("/threads")
async def list_threads(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: GetSession,
) -> list[ThreadOut]:
    return [_thread_out(t) for t in await chats.list_threads(session, user.id)]


@router.post("/threads", status_code=status.HTTP_201_CREATED)
async def create_thread(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: GetSession,
    body: ThreadCreate | None = None,
) -> ThreadOut:
    title = body.title if body else None
    return _thread_out(await chats.create_thread(session, user.id, title))


@router.get("/threads/{thread_id}/messages")
async def list_messages(
    thread_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: GetSession,
) -> list[dict[str, Any]]:
    await chats.get_owned_thread(session, user.id, thread_id)
    return [
        messages_lib.ui_message_from_chat_message(m)
        for m in await chats.list_messages(session, thread_id)
    ]


class ChatStreamRequest(BaseModel):
    """What DefaultChatTransport POSTs; `threadId` rides along via `body`."""

    model_config = ConfigDict(extra="ignore")

    thread_id: UUID = Field(alias="threadId")
    messages: list[dict[str, Any]]


# Kept tiny; tests monkeypatch it to 0.
_STREAM_DELAY_SECONDS = 0.02


def _stub_reply(user_text: str) -> str:
    return (
        f"Stub reply (Phase 3) — you said: “{user_text}”. "
        "Grounded answers with citations arrive in Phase 6."
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


_DONE = "data: [DONE]\n\n"


async def _stub_stream(assistant_id: UUID, text: str):
    """Yield the v1 stream parts for `text`, word by word."""
    yield _sse({"type": "start", "messageId": str(assistant_id)})
    yield _sse({"type": "start-step"})
    text_id = "t0"
    yield _sse({"type": "text-start", "id": text_id})
    for word in text.split(" "):
        yield _sse({"type": "text-delta", "id": text_id, "delta": word + " "})
        await asyncio.sleep(_STREAM_DELAY_SECONDS)
    yield _sse({"type": "text-end", "id": text_id})
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish"})
    yield _DONE


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: GetSession,
) -> StreamingResponse:
    # Ownership + validation happen before the stream opens, so errors reach
    # the client as normal HTTP status codes, not mid-stream error parts.
    thread = await chats.get_owned_thread(session, user.id, payload.thread_id)
    if not payload.messages:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "messages must not be empty")
    try:
        internal = messages_lib.from_ui_message(payload.messages[-1])
    except messages_lib.InvalidUIMessage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    assistant_id = uuid4()
    reply_text = _stub_reply(internal.content)

    async def event_stream():
        async for chunk in _stub_stream(assistant_id, reply_text):
            yield chunk
        # Stream completed successfully — now persist the turn. A client
        # disconnect raises out of the generator and skips this block.
        user_row = ChatMessage(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=internal.content,
            ui_message=payload.messages[-1],
        )
        assistant_row = ChatMessage(
            id=assistant_id,
            thread_id=thread.id,
            role=MessageRole.ASSISTANT,
            content=reply_text,
            ui_message=messages_lib.assistant_ui_message(assistant_id, reply_text),
        )
        await chats.persist_turn(session, thread, user_row, assistant_row)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "Cache-Control": "no-cache",
        },
    )
