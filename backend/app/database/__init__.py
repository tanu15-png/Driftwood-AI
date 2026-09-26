"""Database package: models, Base metadata, and Supabase client helpers."""

from app.database.base import Base
from app.database.models import (
    EMBEDDING_DIMENSIONS,
    ChatMessage,
    ChatThread,
    DocumentChunk,
    MessageCitation,
    MessageRole,
    Profile,
    SourceDocument,
)

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "Base",
    "ChatMessage",
    "ChatThread",
    "DocumentChunk",
    "MessageCitation",
    "MessageRole",
    "Profile",
    "SourceDocument",
]
