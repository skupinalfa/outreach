from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, LargeBinary, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin


class Settings(Base, TimestampMixin):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="settings_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)

    hunter_api_key_ct: Mapped[bytes | None] = mapped_column(LargeBinary)
    openai_api_key_ct: Mapped[bytes | None] = mapped_column(LargeBinary)

    smtp_host: Mapped[str | None] = mapped_column(String)
    smtp_port: Mapped[int | None] = mapped_column(Integer)
    smtp_username_ct: Mapped[bytes | None] = mapped_column(LargeBinary)
    smtp_password_ct: Mapped[bytes | None] = mapped_column(LargeBinary)

    sender_display_name: Mapped[str | None] = mapped_column(String)
    sender_email: Mapped[str | None] = mapped_column(CITEXT)

    follow_up_cadence_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("5")
    )
    default_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("template.id", ondelete="SET NULL")
    )
    openai_model: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'gpt-5.6-luna'")
    )

    master_password_hash: Mapped[str | None] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'Europe/Berlin'")
    )
