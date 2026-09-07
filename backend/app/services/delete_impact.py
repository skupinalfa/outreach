"""Compute the impact counts shown in the delete-confirmation dialog (FR-027a).

Counts are read live from the current state of the tables — no caches — so the numbers
match what the ensuing cascade DELETE will actually remove.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.sent_message import SentMessage
from app.models.todo import Todo, TodoStatus
from app.schemas.delete_impact import DeleteImpactCounts, DeleteImpactOut, DeleteImpactTarget

# open + scheduled together match FR-027a's "open/pending todos (including scheduled follow-ups)".
_PENDING_TODO_STATUSES = (TodoStatus.OPEN, TodoStatus.SCHEDULED)


def organisation_impact(session: Session, org: Organisation) -> DeleteImpactOut:
    contact_ids_q = select(Contact.id).where(Contact.organisation_id == org.id)

    contacts = session.execute(
        select(func.count()).select_from(Contact).where(Contact.organisation_id == org.id)
    ).scalar_one()
    drafts = session.execute(
        select(func.count()).select_from(Draft).where(Draft.contact_id.in_(contact_ids_q))
    ).scalar_one()
    sent_messages = session.execute(
        select(func.count())
        .select_from(SentMessage)
        .where(SentMessage.contact_id.in_(contact_ids_q))
    ).scalar_one()
    open_todos = session.execute(
        select(func.count())
        .select_from(Todo)
        .where(Todo.contact_id.in_(contact_ids_q))
        .where(Todo.status.in_(_PENDING_TODO_STATUSES))
    ).scalar_one()

    return DeleteImpactOut(
        target=DeleteImpactTarget(kind="organisation", id=org.id, name=org.name),
        counts=DeleteImpactCounts(
            contacts=contacts,
            drafts=drafts,
            sent_messages=sent_messages,
            open_todos=open_todos,
        ),
    )


def contact_impact(session: Session, contact: Contact) -> DeleteImpactOut:
    drafts = session.execute(
        select(func.count()).select_from(Draft).where(Draft.contact_id == contact.id)
    ).scalar_one()
    sent_messages = session.execute(
        select(func.count()).select_from(SentMessage).where(SentMessage.contact_id == contact.id)
    ).scalar_one()
    open_todos = session.execute(
        select(func.count())
        .select_from(Todo)
        .where(Todo.contact_id == contact.id)
        .where(Todo.status.in_(_PENDING_TODO_STATUSES))
    ).scalar_one()

    return DeleteImpactOut(
        target=DeleteImpactTarget(
            kind="contact",
            id=contact.id,
            name=f"{contact.first_name} {contact.last_name}".strip(),
        ),
        counts=DeleteImpactCounts(
            contacts=0,
            drafts=drafts,
            sent_messages=sent_messages,
            open_todos=open_todos,
        ),
    )
