"""Chat REST + streaming routes.

Stream wire format: AI SDK UI message stream v1 (SSE) — `start`, `start-step`,
`text-start`/`text-delta`/`text-end`, `finish-step`, `finish`, `[DONE]` —
which `useChat` + `DefaultChatTransport` consume directly.
"""

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.assistant.runtime import AssistantRuntime, get_runtime
from app.auth import CurrentUser, GetSession, get_current_user
from app.chat import messages as messages_lib
from app.chat.orchestrator import prepare_turn, stream_turn
from app.database import chats

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


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: GetSession,
) -> Response:
    await chats.delete_thread(session, user.id, thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ChatStreamRequest(BaseModel):
    """What DefaultChatTransport POSTs; `threadId` rides along via `body`."""

    model_config = ConfigDict(extra="ignore")

    thread_id: UUID = Field(alias="threadId")
    messages: list[dict[str, Any]]


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: GetSession,
    runtime: Annotated[AssistantRuntime, Depends(get_runtime)],
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

    turn = await prepare_turn(session, user, thread.id, internal.content, runtime)

    return StreamingResponse(
        stream_turn(session, thread, payload.messages[-1], internal.content, uuid4(), turn),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "Cache-Control": "no-cache",
        },
    )
