"""org cascade delete

Switches contact.organisation_id FK from ON DELETE RESTRICT to ON DELETE CASCADE so that
deleting an organisation atomically removes all of its contacts (which in turn cascade to
drafts, sent_messages, and todos via their own FKs). Backs spec FR-001, data-model.md
"GDPR Erasure & Cascade Delete", and research.md R14.

Revision ID: 0002_org_cascade
Revises: 0001_initial
Create Date: 2026-09-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_org_cascade"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The canonical FK name under the app's metadata naming convention (see app/db.py):
#   fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s
FK_NAME = "fk_contact_organisation_id_organisation"


def _replace_fk(new_ondelete: str) -> None:
    # Drop whichever FK on contact.organisation_id exists — the 0001 migration created it
    # via inline `sa.ForeignKey(...)`, and depending on Alembic's naming-convention
    # propagation it may have landed as `fk_contact_organisation_id_organisation` or as
    # Postgres' default `contact_organisation_id_fkey`. Introspect and drop by whatever
    # name it actually has.
    op.execute(
        """
        DO $$
        DECLARE
            fk_name text;
        BEGIN
            SELECT c.conname INTO fk_name
            FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
            WHERE c.conrelid = 'contact'::regclass
              AND c.contype  = 'f'
              AND a.attname  = 'organisation_id'
            LIMIT 1;
            IF fk_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE contact DROP CONSTRAINT %I', fk_name);
            END IF;
        END $$;
        """
    )
    op.create_foreign_key(
        FK_NAME,
        source_table="contact",
        referent_table="organisation",
        local_cols=["organisation_id"],
        remote_cols=["id"],
        ondelete=new_ondelete,
    )


def upgrade() -> None:
    _replace_fk("CASCADE")


def downgrade() -> None:
    _replace_fk("RESTRICT")
