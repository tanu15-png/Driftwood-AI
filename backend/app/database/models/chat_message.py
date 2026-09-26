import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.models.message_role import MessageRole


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    # Named so the migration renders a stable ck_chat_messages_role_allowed name.
    __table_args__ = (
        CheckConstraint(
            "role::text = ANY (ARRAY['user'::text, 'assistant'::text])",
            name="role_allowed",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # DB-level guard matching MessageRole; migration mirrors this constraint.
    role: Mapped[MessageRole] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ui_message: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
