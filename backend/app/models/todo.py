from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.contact import Contact
    from app.models.draft import Draft
    from app.models.sent_message import SentMessage


class TodoType(str, enum.Enum):
    SEND = "send"
    FOLLOW_UP = "follow_up"
    MANUAL = "manual"


class TodoStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class Todo(Base, TimestampMixin):
    __tablename__ = "todo"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[TodoType] = mapped_column(
        Enum(
            TodoType,
            name="todo_type",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), nullable=False
    )
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("draft.id", ondelete="SET NULL"))
    sent_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("sent_message.id", ondelete="SET NULL")
    )

    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[TodoStatus] = mapped_column(
        Enum(
            TodoStatus,
            name="todo_status",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        server_default=TodoStatus.OPEN.value,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How the todo reached its terminal state. NULL while `status IN ('scheduled','open')`.
    # Vocabulary: 'sent' | 'mailbox_stored' | 'manual' | 'cancelled_by_status_change'.
    # Not a Postgres enum — see research.md R7.
    completed_via: Mapped[str | None] = mapped_column(String)

    contact: Mapped[Contact] = relationship(back_populates="todos")
    draft: Mapped[Draft | None] = relationship()
    sent_message: Mapped[SentMessage | None] = relationship()

    __table_args__ = (
        Index("ix_todo_status_due_at", "status", "due_at"),
        Index("ix_todo_contact_id_status", "contact_id", "status"),
    )
