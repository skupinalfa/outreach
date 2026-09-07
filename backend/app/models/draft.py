from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.contact import Contact
    from app.models.prompt import Prompt
    from app.models.template import Template


class Draft(Base, TimestampMixin):
    __tablename__ = "draft"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contact.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("template.id", ondelete="RESTRICT"), nullable=False
    )
    template_body_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("prompt.id", ondelete="RESTRICT"), nullable=False
    )
    prompt_text_snapshot: Mapped[str] = mapped_column(String, nullable=False)

    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    contact: Mapped[Contact] = relationship(back_populates="drafts")
    template: Mapped[Template] = relationship()
    prompt: Mapped[Prompt] = relationship()

    __table_args__ = (Index("ix_draft_contact_id", "contact_id"),)
