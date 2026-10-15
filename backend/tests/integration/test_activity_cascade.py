"""Cascade-delete tests for activity events (T041, FR-051).

Verifies:
- Deleting a contact removes its activity_event rows (direct FK cascade).
- Deleting an organisation cascades through contacts to activity_event.
- No orphan rows remain after either cascade.
"""
from __future__ import annotations

from sqlalchemy import select

from app.models.activity_event import ActivityActor, ActivityEvent, ActivityEventType
from app.models.contact import Contact
from app.models.organisation import Organisation
from app.services import activity as activity_service


def _seed(session_factory) -> tuple[int, int, int]:
    """Seed one org + one contact + 3 activity events. Returns (org_id, contact_id, event_count)."""
    with session_factory() as s:
        org = Organisation(name="Cas", domain="cas.example")
        s.add(org)
        s.flush()
        c = Contact(
            organisation_id=org.id,
            first_name="C",
            last_name="C",
            email="c@cas.example",
        )
        s.add(c)
        s.flush()
        for _ in range(3):
            activity_service.record_event(
                s,
                contact_id=c.id,
                organisation_id=org.id,
                event_type=ActivityEventType.LEAD_CREATED,
                actor=ActivityActor.OPERATOR,
            )
        s.commit()
        return org.id, c.id, 3


def test_contact_delete_cascades_to_activity_events(session_factory) -> None:
    org_id, contact_id, count = _seed(session_factory)

    with session_factory() as s:
        assert (
            s.execute(
                select(ActivityEvent).where(ActivityEvent.contact_id == contact_id)
            ).scalars().all().__len__()
            == count
        )
        contact = s.get(Contact, contact_id)
        s.delete(contact)
        s.commit()

    with session_factory() as s:
        remaining = (
            s.execute(select(ActivityEvent).where(ActivityEvent.contact_id == contact_id))
            .scalars()
            .all()
        )
        assert remaining == []
        # Org survives; its count is now 0.
        assert activity_service.count_for_organisation(s, org_id) == 0


def test_organisation_delete_cascades_to_activity_events_via_contact(session_factory) -> None:
    org_id, contact_id, _ = _seed(session_factory)

    with session_factory() as s:
        org = s.get(Organisation, org_id)
        s.delete(org)
        s.commit()

    with session_factory() as s:
        # No activity events remain for either the org or the contact.
        assert s.execute(
            select(ActivityEvent).where(ActivityEvent.organisation_id == org_id)
        ).scalars().all() == []
        assert s.execute(
            select(ActivityEvent).where(ActivityEvent.contact_id == contact_id)
        ).scalars().all() == []


def test_no_orphan_activity_events_after_cascade(session_factory) -> None:
    """FR-051 — no `activity_event` rows may reference a deleted contact."""
    _seed(session_factory)
    with session_factory() as s:
        # Delete the only contact.
        contact = s.execute(select(Contact)).scalar_one()
        s.delete(contact)
        s.commit()

    with session_factory() as s:
        orphans = s.execute(
            select(ActivityEvent).where(
                ActivityEvent.contact_id.notin_(select(Contact.id))
            )
        ).scalars().all()
        assert orphans == []
