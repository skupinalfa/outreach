from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Prompt(Base, TimestampMixin):
    __tablename__ = "prompt"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(sa.String, nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())

    __table_args__ = (
        sa.Index(
            "uq_prompt_is_active",
            "is_active",
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        ),
    )
