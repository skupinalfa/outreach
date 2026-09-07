from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.contact import Contact


class DeliveryStatus(str, enum.Enum):
    SENT = "sent"
    BOUNCED = "bounced"
    FAILED = "failed"


class SentMessage(Base, TimestampMixin):
    __tablename__ = "sent_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)

    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivery_status: Mapped[str] = mapped_column(String, nullable=False, default=DeliveryStatus.SENT.value)
    error: Mapped[str | None] = mapped_column(String)

    contact: Mapped[Contact] = relationship(back_populates="sent_messages")

    __table_args__ = (
        Index("ix_sent_message_contact_id_sent_at", "contact_id", text("sent_at DESC")),
        Index("ix_sent_message_sent_at", "sent_at"),
    )
