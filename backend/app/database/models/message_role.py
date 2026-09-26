from enum import StrEnum


class MessageRole(StrEnum):
    """Allowed values for ``chat_messages.role``."""

    USER = "user"
    ASSISTANT = "assistant"
