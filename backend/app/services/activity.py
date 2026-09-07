"""Activity-event write + count helpers (FR-038, FR-051, FR-052).

Every write-path service calls `record_event(...)` from inside its own DB transaction, so the
activity log commits atomically with the natural entity write. There is no dispatcher, queue, or
background writer — that would open a partial-failure window (research.md R1).

The count helpers back the `activity_events` field of `DeleteImpactCounts` (FR-052) — read
live from the table, no caches.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.activity_event import ActivityActor, ActivityEvent, ActivityEventType


def record_event(
    session: Session,
    *,
    contact_id: int,
    organisation_id: int,
    event_type: ActivityEventType,
    actor: ActivityActor,
    payload: dict[str, Any] | None = None,
) -> ActivityEvent:
    """Insert an activity event using the caller's session, without commit.

    The event participates in whatever transaction the caller has open. If the enclosing
    transaction rolls back (e.g. an SMTP send raised after the sent_message INSERT), this
    event rolls back with it — guaranteeing the log never diverges from what actually
    happened (FR-038 / Constitution IV).
    """
    event = ActivityEvent(
        contact_id=contact_id,
        organisation_id=organisation_id,
        event_type=event_type,
        actor=actor,
        payload=payload or {},
    )
    session.add(event)
    return event


def count_for_contact(session: Session, contact_id: int) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityEvent)
        .where(ActivityEvent.contact_id == contact_id)
    ).scalar_one()


def count_for_organisation(session: Session, organisation_id: int) -> int:
    return session.execute(
        select(func.count())
        .select_from(ActivityEvent)
        .where(ActivityEvent.organisation_id == organisation_id)
    ).scalar_one()
