"""AI SDK UI messages ↔ internal chat message types.

The frontend speaks AI SDK v5 `UIMessage` shape:
`{ id, role, parts: [{ type: "text", text }] }`. We persist the plain-text
content plus the raw UI message (JSONB) so richer parts (citations, Phase 6)
replay verbatim later.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.database.models import ChatMessage, MessageRole

_TEXT_PART = "text"


class InvalidUIMessage(ValueError):
    """A client-sent UI message we cannot turn into a chat message."""


@dataclass(frozen=True)
class InternalMessage:
    role: MessageRole
    content: str


def _text_from_parts(parts: object) -> str:
    if not isinstance(parts, list):
        return ""
    texts = (
        part.get("text", "")
        for part in parts
        if isinstance(part, dict)
        and part.get("type") == _TEXT_PART
        and isinstance(part.get("text"), str)
    )
    return "".join(texts).strip()


def from_ui_message(raw: object) -> InternalMessage:
    """Validate a client-sent UIMessage and extract (role, text).

    Only user messages are accepted — assistant turns are server-generated.
    """
    if not isinstance(raw, dict):
        raise InvalidUIMessage("message must be a JSON object")
    if raw.get("role") != MessageRole.USER:
        raise InvalidUIMessage(
            f"only user messages are accepted, got role {raw.get('role')!r}"
        )
    content = _text_from_parts(raw.get("parts"))
    if not content:
        raise InvalidUIMessage("message must contain a non-empty text part")
    return InternalMessage(role=MessageRole.USER, content=content)


def ui_message_from_chat_message(message: ChatMessage) -> dict[str, Any]:
    """The AI SDK UIMessage for a persisted message: stored raw when present."""
    if message.ui_message is not None:
        return message.ui_message
    return {
        "id": str(message.id),
        "role": str(message.role),
        "parts": [{"type": _TEXT_PART, "text": message.content}],
    }


def assistant_ui_message(message_id: UUID, text: str) -> dict[str, Any]:
    """UIMessage for a server-generated reply (id == persisted message id)."""
    return {
        "id": str(message_id),
        "role": str(MessageRole.ASSISTANT),
        "parts": [{"type": _TEXT_PART, "text": text}],
    }
