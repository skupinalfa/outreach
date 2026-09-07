"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONTACT_STATUS = ("new", "enriched", "contacted", "replied", "not_interested", "meeting_booked")
TODO_TYPE = ("send", "follow_up", "manual")
TODO_STATUS = ("scheduled", "open", "done", "cancelled")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    contact_status = postgresql.ENUM(*CONTACT_STATUS, name="contact_status", create_type=False)
    todo_type = postgresql.ENUM(*TODO_TYPE, name="todo_type", create_type=False)
    todo_status = postgresql.ENUM(*TODO_STATUS, name="todo_status", create_type=False)
    bind = op.get_bind()
    postgresql.ENUM(*CONTACT_STATUS, name="contact_status").create(bind, checkfirst=True)
    postgresql.ENUM(*TODO_TYPE, name="todo_type").create(bind, checkfirst=True)
    postgresql.ENUM(*TODO_STATUS, name="todo_status").create(bind, checkfirst=True)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.create_table(
        "organisation",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("CREATE UNIQUE INDEX uq_organisation_name_lower ON organisation (lower(name))")
    op.create_index("ix_organisation_domain", "organisation", ["domain"])

    op.create_table(
        "template",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("subject_hint", sa.String(), nullable=True),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_template_name_lower_active "
        "ON template (lower(name)) WHERE is_archived = false"
    )

    op.create_table(
        "prompt",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("CREATE UNIQUE INDEX uq_prompt_is_active ON prompt (is_active) WHERE is_active = true")

    op.create_table(
        "contact",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "organisation_id",
            sa.BigInteger(),
            sa.ForeignKey("organisation.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(), nullable=False),
        sa.Column("last_name", sa.String(), nullable=False),
        sa.Column("gender", sa.String(length=1), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("position", sa.String(), nullable=True),
        sa.Column("status", contact_status, nullable=False, server_default="new"),
        sa.Column("notes", sa.String(), nullable=False, server_default=""),
        sa.Column("last_enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_enrichment_error", sa.String(), nullable=True),
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_generation_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_contact_org_email_lower "
        "ON contact (organisation_id, lower(email)) WHERE email IS NOT NULL"
    )
    op.create_index("ix_contact_organisation_id", "contact", ["organisation_id"])
    op.create_index("ix_contact_status", "contact", ["status"])

    op.create_table(
        "draft",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("contact_id", sa.BigInteger(), sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey("template.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_body_snapshot", sa.String(), nullable=False),
        sa.Column("prompt_id", sa.BigInteger(), sa.ForeignKey("prompt.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("prompt_text_snapshot", sa.String(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_draft_contact_id", "draft", ["contact_id"])

    op.create_table(
        "sent_message",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("contact_id", sa.BigInteger(), sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivery_status", sa.String(), nullable=False, server_default="sent"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "CREATE INDEX ix_sent_message_contact_id_sent_at ON sent_message (contact_id, sent_at DESC)"
    )
    op.create_index("ix_sent_message_sent_at", "sent_message", ["sent_at"])

    op.create_table(
        "todo",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("type", todo_type, nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("contact_id", sa.BigInteger(), sa.ForeignKey("contact.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft_id", sa.BigInteger(), sa.ForeignKey("draft.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "sent_message_id",
            sa.BigInteger(),
            sa.ForeignKey("sent_message.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", todo_status, nullable=False, server_default="open"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_todo_status_due_at", "todo", ["status", "due_at"])
    op.create_index("ix_todo_contact_id_status", "todo", ["contact_id", "status"])

    op.create_table(
        "settings",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("hunter_api_key_ct", sa.LargeBinary(), nullable=True),
        sa.Column("openai_api_key_ct", sa.LargeBinary(), nullable=True),
        sa.Column("smtp_host", sa.String(), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=True),
        sa.Column("smtp_username_ct", sa.LargeBinary(), nullable=True),
        sa.Column("smtp_password_ct", sa.LargeBinary(), nullable=True),
        sa.Column("sender_display_name", sa.String(), nullable=True),
        sa.Column("sender_email", postgresql.CITEXT(), nullable=True),
        sa.Column("follow_up_cadence_days", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column(
            "default_template_id",
            sa.BigInteger(),
            sa.ForeignKey("template.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("openai_model", sa.String(), nullable=False, server_default="gpt-5.6-luna"),
        sa.Column("master_password_hash", sa.String(), nullable=True),
        sa.Column("timezone", sa.String(), nullable=False, server_default="Europe/Berlin"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="settings_singleton"),
    )

    op.create_table(
        "session",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_session_expires_at", "session", ["expires_at"])

    for tbl in (
        "organisation",
        "template",
        "prompt",
        "contact",
        "draft",
        "sent_message",
        "todo",
        "settings",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{tbl}_updated_at "
            f"BEFORE UPDATE ON {tbl} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for tbl in (
        "settings",
        "todo",
        "sent_message",
        "draft",
        "contact",
        "prompt",
        "template",
        "organisation",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tbl}_updated_at ON {tbl}")

    op.drop_index("ix_session_expires_at", table_name="session")
    op.drop_table("session")
    op.drop_table("settings")
    op.drop_index("ix_todo_contact_id_status", table_name="todo")
    op.drop_index("ix_todo_status_due_at", table_name="todo")
    op.drop_table("todo")
    op.drop_index("ix_sent_message_sent_at", table_name="sent_message")
    op.execute("DROP INDEX IF EXISTS ix_sent_message_contact_id_sent_at")
    op.drop_table("sent_message")
    op.drop_index("ix_draft_contact_id", table_name="draft")
    op.drop_table("draft")
    op.drop_index("ix_contact_status", table_name="contact")
    op.drop_index("ix_contact_organisation_id", table_name="contact")
    op.execute("DROP INDEX IF EXISTS uq_contact_org_email_lower")
    op.drop_table("contact")
    op.execute("DROP INDEX IF EXISTS uq_prompt_is_active")
    op.drop_table("prompt")
    op.execute("DROP INDEX IF EXISTS uq_template_name_lower_active")
    op.drop_table("template")
    op.drop_index("ix_organisation_domain", table_name="organisation")
    op.execute("DROP INDEX IF EXISTS uq_organisation_name_lower")
    op.drop_table("organisation")

    for enum_name in ("todo_status", "todo_type", "contact_status"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")

    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
