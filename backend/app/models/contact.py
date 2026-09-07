from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.draft import Draft
    from app.models.organisation import Organisation
    from app.models.sent_message import SentMessage
    from app.models.todo import Todo


class ContactStatus(str, enum.Enum):
    NEW = "new"
    ENRICHED = "enriched"
    CONTACTED = "contacted"
    REPLIED = "replied"
    NOT_INTERESTED = "not_interested"
    MEETING_BOOKED = "meeting_booked"


class Contact(Base, TimestampMixin):
    __tablename__ = "contact"

    id: Mapped[int] = mapped_column(primary_key=True)
    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisation.id", ondelete="RESTRICT"),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(1))
    email: Mapped[str | None] = mapped_column(CITEXT)
    position: Mapped[str | None] = mapped_column(String)
    status: Mapped[ContactStatus] = mapped_column(
        Enum(
            ContactStatus,
            name="contact_status",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        server_default=ContactStatus.NEW.value,
    )
    notes: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))

    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_enrichment_error: Mapped[str | None] = mapped_column(String)
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_generation_error: Mapped[str | None] = mapped_column(String)

    organisation: Mapped[Organisation] = relationship(back_populates="contacts")
    drafts: Mapped[list[Draft]] = relationship(
        back_populates="contact",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sent_messages: Mapped[list[SentMessage]] = relationship(
        back_populates="contact",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    todos: Mapped[list[Todo]] = relationship(
        back_populates="contact",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index(
            "uq_contact_org_email_lower",
            "organisation_id",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index("ix_contact_organisation_id", "organisation_id"),
        Index("ix_contact_status", "status"),
    )
