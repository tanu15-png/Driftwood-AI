"""Unit tests for AI SDK UI message mapping. No network, no DB."""

import pytest

from app.chat.messages import (
    InvalidUIMessage,
    assistant_ui_message,
    from_ui_message,
    ui_message_from_chat_message,
)
from app.database.models import ChatMessage, MessageRole


def test_user_text_part_extracts_content() -> None:
    internal = from_ui_message(
        {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "  hello  "}]}
    )
    assert internal.role is MessageRole.USER
    assert internal.content == "hello"


def test_multiple_text_parts_concatenate() -> None:
    internal = from_ui_message(
        {
            "role": "user",
            "parts": [
                {"type": "text", "text": "a"},
                {"type": "step-boundary"},
                {"type": "text", "text": "b"},
            ],
        }
    )
    assert internal.content == "ab"


def test_rejects_non_user_role() -> None:
    with pytest.raises(InvalidUIMessage):
        from_ui_message(
            {"role": "assistant", "parts": [{"type": "text", "text": "hi"}]}
        )


def test_rejects_empty_text() -> None:
    with pytest.raises(InvalidUIMessage):
        from_ui_message({"role": "user", "parts": [{"type": "text", "text": "   "}]})


def test_rejects_non_dict() -> None:
    with pytest.raises(InvalidUIMessage):
        from_ui_message("not a dict")


def test_rejects_missing_parts() -> None:
    with pytest.raises(InvalidUIMessage):
        from_ui_message({"role": "user"})


def test_ui_message_from_chat_message_falls_back_to_synthetic() -> None:
    message = ChatMessage(id=_uuid(), role=MessageRole.USER, content="hey")
    ui = ui_message_from_chat_message(message)
    assert ui == {"id": str(message.id), "role": "user", "parts": [{"type": "text", "text": "hey"}]}


def test_ui_message_from_chat_message_prefers_stored_raw() -> None:
    raw = {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "hey"}]}
    message = ChatMessage(
        id=_uuid(), role=MessageRole.USER, content="hey", ui_message=raw
    )
    assert ui_message_from_chat_message(message) == raw


def test_assistant_ui_message_shape() -> None:
    from uuid import uuid4

    message_id = uuid4()
    ui = assistant_ui_message(message_id, "hello there")
    assert ui == {
        "id": str(message_id),
        "role": "assistant",
        "parts": [{"type": "text", "text": "hello there"}],
    }


def _uuid():
    from uuid import uuid4

    return uuid4()
