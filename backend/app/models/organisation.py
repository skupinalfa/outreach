from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.contact import Contact


class Organisation(Base, TimestampMixin):
    __tablename__ = "organisation"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))

    contacts: Mapped[list[Contact]] = relationship(
        back_populates="organisation",
        cascade="all",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("uq_organisation_name_lower", text("lower(name)"), unique=True),
        Index("ix_organisation_domain", "domain"),
    )
