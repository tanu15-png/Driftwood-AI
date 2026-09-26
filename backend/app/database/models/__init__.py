"""SQLAlchemy models. Importing this package registers all tables on Base.metadata."""

from app.database.base import Base
from app.database.models.chat_message import ChatMessage
from app.database.models.chat_thread import ChatThread
from app.database.models.constants import EMBEDDING_DIMENSIONS
from app.database.models.document_chunk import DocumentChunk
from app.database.models.message_citation import MessageCitation
from app.database.models.message_role import MessageRole
from app.database.models.source_document import SourceDocument
from app.database.models.user import Profile

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
