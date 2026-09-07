"""activity_event + save-to-mailbox schema (feature 002)

Adds the activity log used by both the per-contact Activity view (US1) and the cross-contact
Activity screen (US2), plus additive columns that support the "Save draft to mail account"
option (US3):

  * new table `activity_event` with two enums (`activity_event_type`, `activity_actor`),
    four indexes, and cascade FKs on `contact_id` and `organisation_id` — see
    specs/002-activity-view-drafts/data-model.md.
  * `draft`  +mailbox_folder / mailbox_uid / mailbox_stored_at         (US3, FR-046 / FR-049)
  * `todo`   +completed_via                                            (US3, FR-046 / SC-014)
  * `settings` +imap_host / imap_port / imap_username_ct / imap_password_ct
              / imap_use_tls / imap_drafts_folder / imap_drafts_folder_detected
                                                                        (US3, FR-050)

Revision ID: 0003_activity_and_imap
Revises: 0002_org_cascade
Create Date: 2026-09-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_activity_and_imap"
down_revision: Union[str, None] = "0002_org_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ACTIVITY_EVENT_TYPES = (
    "lead_created",
    "enrichment_attempted",
    "draft_generated",
    "draft_regenerated",
    "draft_stored_in_mailbox",
    "mailbox_store_failed",
    "email_sent",
    "send_failed",
    "todo_created",
    "todo_completed",
    "todo_cancelled",
    "follow_up_scheduled",
    "status_changed",
)
ACTIVITY_ACTORS = ("operator", "system")


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*ACTIVITY_EVENT_TYPES, name="activity_event_type").create(bind, checkfirst=True)
    postgresql.ENUM(*ACTIVITY_ACTORS, name="activity_actor").create(bind, checkfirst=True)

    activity_event_type = postgresql.ENUM(
        *ACTIVITY_EVENT_TYPES, name="activity_event_type", create_type=False
    )
    activity_actor = postgresql.ENUM(*ACTIVITY_ACTORS, name="activity_actor", create_type=False)

    op.create_table(
        "activity_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "contact_id",
            sa.BigInteger(),
            sa.ForeignKey("contact.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organisation_id",
            sa.BigInteger(),
            sa.ForeignKey("organisation.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", activity_event_type, nullable=False),
        sa.Column("actor", activity_actor, nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Global-timeline default sort + keyset pagination cursor (research.md R9).
    op.execute(
        "CREATE INDEX ix_activity_event_ts "
        "ON activity_event (occurred_at DESC, id DESC)"
    )
    # Per-contact Activity view (FR-040).
    op.execute(
        "CREATE INDEX ix_activity_event_contact_ts "
        "ON activity_event (contact_id, occurred_at DESC)"
    )
    # Organisation-filtered global view (FR-042).
    op.execute(
        "CREATE INDEX ix_activity_event_org_ts "
        "ON activity_event (organisation_id, occurred_at DESC)"
    )
    # Event-type-filtered global view (FR-042).
    op.execute(
        "CREATE INDEX ix_activity_event_type_ts "
        "ON activity_event (event_type, occurred_at DESC)"
    )

    op.add_column("draft", sa.Column("mailbox_folder", sa.String(), nullable=True))
    op.add_column("draft", sa.Column("mailbox_uid", sa.BigInteger(), nullable=True))
    op.add_column(
        "draft", sa.Column("mailbox_stored_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column("todo", sa.Column("completed_via", sa.String(), nullable=True))

    op.add_column("settings", sa.Column("imap_host", sa.String(), nullable=True))
    op.add_column("settings", sa.Column("imap_port", sa.Integer(), nullable=True))
    op.add_column("settings", sa.Column("imap_username_ct", sa.LargeBinary(), nullable=True))
    op.add_column("settings", sa.Column("imap_password_ct", sa.LargeBinary(), nullable=True))
    op.add_column(
        "settings",
        sa.Column("imap_use_tls", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("settings", sa.Column("imap_drafts_folder", sa.String(), nullable=True))
    op.add_column(
        "settings", sa.Column("imap_drafts_folder_detected", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("settings", "imap_drafts_folder_detected")
    op.drop_column("settings", "imap_drafts_folder")
    op.drop_column("settings", "imap_use_tls")
    op.drop_column("settings", "imap_password_ct")
    op.drop_column("settings", "imap_username_ct")
    op.drop_column("settings", "imap_port")
    op.drop_column("settings", "imap_host")

    op.drop_column("todo", "completed_via")

    op.drop_column("draft", "mailbox_stored_at")
    op.drop_column("draft", "mailbox_uid")
    op.drop_column("draft", "mailbox_folder")

    op.execute("DROP INDEX IF EXISTS ix_activity_event_type_ts")
    op.execute("DROP INDEX IF EXISTS ix_activity_event_org_ts")
    op.execute("DROP INDEX IF EXISTS ix_activity_event_contact_ts")
    op.execute("DROP INDEX IF EXISTS ix_activity_event_ts")
    op.drop_table("activity_event")

    op.execute("DROP TYPE IF EXISTS activity_actor")
    op.execute("DROP TYPE IF EXISTS activity_event_type")
