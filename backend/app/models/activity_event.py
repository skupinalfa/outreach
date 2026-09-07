from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.contact import Contact
    from app.models.organisation import Organisation


class ActivityEventType(str, enum.Enum):
    LEAD_CREATED = "lead_created"
    ENRICHMENT_ATTEMPTED = "enrichment_attempted"
    DRAFT_GENERATED = "draft_generated"
    DRAFT_REGENERATED = "draft_regenerated"
    DRAFT_STORED_IN_MAILBOX = "draft_stored_in_mailbox"
    MAILBOX_STORE_FAILED = "mailbox_store_failed"
    EMAIL_SENT = "email_sent"
    SEND_FAILED = "send_failed"
    TODO_CREATED = "todo_created"
    TODO_COMPLETED = "todo_completed"
    TODO_CANCELLED = "todo_cancelled"
    FOLLOW_UP_SCHEDULED = "follow_up_scheduled"
    STATUS_CHANGED = "status_changed"


class ActivityActor(str, enum.Enum):
    OPERATOR = "operator"
    SYSTEM = "system"


class ActivityEvent(Base):
    __tablename__ = "activity_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contact.id", ondelete="CASCADE"),
        nullable=False,
    )
    organisation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organisation.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[ActivityEventType] = mapped_column(
        Enum(
            ActivityEventType,
            name="activity_event_type",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    actor: Mapped[ActivityActor] = mapped_column(
        Enum(
            ActivityActor,
            name="activity_actor",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contact: Mapped[Contact] = relationship()
    organisation: Mapped[Organisation] = relationship()
