from __future__ import annotations

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Template(Base, TimestampMixin):
    __tablename__ = "template"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    subject_hint: Mapped[str | None] = mapped_column(String)
    body: Mapped[str] = mapped_column(String, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        Index(
            "uq_template_name_lower_active",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("is_archived = false"),
        ),
    )
