"""Activity trace endpoints (feature 002, FR-040 / FR-041 / FR-042).

Two routes share this file:
- `GET /api/v1/contacts/{id}/activity` — per-contact timeline (T017 / US1)
- `GET /api/v1/activity`               — cross-contact timeline (T036 / US2)

Both return the unified `ActivityEventView` shape; message-carrying events (`email_sent`,
`draft_generated`, `draft_regenerated`, `draft_stored_in_mailbox`) carry a `message_snapshot`
joined from `sent_message` / `draft` at read time (data-model.md § Illustrative queries).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.errors import api_error, not_found
from app.db import get_db
from app.models.activity_event import ActivityEvent, ActivityEventType
from app.models.contact import Contact
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.sent_message import SentMessage
from app.schemas.activity import (
    ActivityEventView,
    ActivityFilter,
    ContactActivityOut,
    ContactRef,
    ContactRefWithOrg,
    GlobalActivityOut,
    MessageSnapshot,
    OrganisationRef,
    WindowPreset,
    decode_cursor,
    encode_cursor,
)
from app.security.auth import require_auth

router = APIRouter(tags=["activity"], dependencies=[Depends(require_auth)])


_MESSAGE_EVENT_TYPES = {
    ActivityEventType.EMAIL_SENT,
    ActivityEventType.DRAFT_GENERATED,
    ActivityEventType.DRAFT_REGENERATED,
    ActivityEventType.DRAFT_STORED_IN_MAILBOX,
}


def _summary_for(event: ActivityEvent, contact: Contact, org: Organisation | None) -> str:
    """Human-readable one-liner rendered as the event row header (English, v1)."""
    name = f"{contact.first_name} {contact.last_name}".strip()
    org_name = org.name if org is not None else ""
    payload = event.payload or {}
    t = event.event_type
    if t == ActivityEventType.LEAD_CREATED:
        return f"Lead created for {name}" + (f" at {org_name}" if org_name else "")
    if t == ActivityEventType.ENRICHMENT_ATTEMPTED:
        outcome = payload.get("outcome", "unknown")
        return f"Enrichment attempted — {outcome}"
    if t == ActivityEventType.DRAFT_GENERATED:
        tpl = payload.get("template_name") or f"template #{payload.get('template_id')}"
        return f"Draft generated using {tpl}"
    if t == ActivityEventType.DRAFT_REGENERATED:
        tpl = payload.get("template_name") or f"template #{payload.get('template_id')}"
        return f"Draft regenerated using {tpl}"
    if t == ActivityEventType.DRAFT_STORED_IN_MAILBOX:
        folder = payload.get("folder_path", "Drafts")
        return f"Draft saved to mailbox — {folder}"
    if t == ActivityEventType.MAILBOX_STORE_FAILED:
        reason = payload.get("reason", "unknown reason")
        return f"Save to mailbox failed — {reason}"
    if t == ActivityEventType.EMAIL_SENT:
        recipient = payload.get("recipient", "recipient")
        return f"Email sent to {recipient}"
    if t == ActivityEventType.SEND_FAILED:
        reason = payload.get("reason", "unknown reason")
        return f"Send failed — {reason}"
    if t == ActivityEventType.TODO_CREATED:
        return f"Todo created ({payload.get('todo_type', 'todo')})"
    if t == ActivityEventType.TODO_COMPLETED:
        via = payload.get("completion_via", "manual")
        return f"Todo completed ({via})"
    if t == ActivityEventType.TODO_CANCELLED:
        reason = payload.get("reason", "cancelled")
        return f"Todo cancelled ({reason})"
    if t == ActivityEventType.FOLLOW_UP_SCHEDULED:
        return "Follow-up scheduled"
    if t == ActivityEventType.STATUS_CHANGED:
        return f"Status changed: {payload.get('from', '?')} → {payload.get('to', '?')}"
    return t.value


def _serialise(
    event: ActivityEvent,
    contact: Contact,
    org: Organisation | None,
    snapshot: MessageSnapshot | None,
) -> ActivityEventView:
    return ActivityEventView(
        id=event.id,
        event_type=event.event_type,
        actor=event.actor,
        occurred_at=event.occurred_at,
        contact=ContactRef(
            id=contact.id, first_name=contact.first_name, last_name=contact.last_name
        ),
        organisation=OrganisationRef(id=org.id, name=org.name) if org is not None else None,
        summary=_summary_for(event, contact, org),
        payload=event.payload or {},
        message_snapshot=snapshot,
    )


def _snapshot_for(
    event: ActivityEvent,
    sent_messages: dict[int, SentMessage],
    drafts: dict[int, Draft],
) -> MessageSnapshot | None:
    if event.event_type not in _MESSAGE_EVENT_TYPES:
        return None
    payload = event.payload or {}
    if event.event_type == ActivityEventType.EMAIL_SENT:
        sm_id = payload.get("sent_message_id")
        sm = sent_messages.get(sm_id) if sm_id is not None else None
        if sm is None:
            return None
        return MessageSnapshot(subject=sm.subject, body=sm.body, delivery_status=sm.delivery_status)
    draft_id = payload.get("draft_id")
    d = drafts.get(draft_id) if draft_id is not None else None
    if d is None:
        return None
    return MessageSnapshot(subject=d.subject, body=d.body, delivery_status=None)


def _hydrate_snapshots(
    db: Session, events: list[ActivityEvent]
) -> tuple[dict[int, SentMessage], dict[int, Draft]]:
    """Batch-load the sent_message / draft rows referenced by the visible events."""
    sm_ids: set[int] = set()
    draft_ids: set[int] = set()
    for ev in events:
        payload = ev.payload or {}
        if ev.event_type == ActivityEventType.EMAIL_SENT:
            sm_id = payload.get("sent_message_id")
            if isinstance(sm_id, int):
                sm_ids.add(sm_id)
        elif ev.event_type in _MESSAGE_EVENT_TYPES:
            draft_id = payload.get("draft_id")
            if isinstance(draft_id, int):
                draft_ids.add(draft_id)
    sent_messages: dict[int, SentMessage] = {}
    if sm_ids:
        for sm in db.execute(select(SentMessage).where(SentMessage.id.in_(sm_ids))).scalars():
            sent_messages[sm.id] = sm
    drafts: dict[int, Draft] = {}
    if draft_ids:
        for d in db.execute(select(Draft).where(Draft.id.in_(draft_ids))).scalars():
            drafts[d.id] = d
    return sent_messages, drafts


def _hydrate_contacts(
    db: Session, events: list[ActivityEvent]
) -> tuple[dict[int, Contact], dict[int, Organisation]]:
    contact_ids = {ev.contact_id for ev in events}
    org_ids = {ev.organisation_id for ev in events}
    contacts: dict[int, Contact] = {}
    orgs: dict[int, Organisation] = {}
    if contact_ids:
        for c in db.execute(select(Contact).where(Contact.id.in_(contact_ids))).scalars():
            contacts[c.id] = c
    if org_ids:
        for o in db.execute(select(Organisation).where(Organisation.id.in_(org_ids))).scalars():
            orgs[o.id] = o
    return contacts, orgs


def _apply_window(
    since: datetime | None, until: datetime | None, window: WindowPreset | None
) -> tuple[datetime | None, datetime | None]:
    if window is None:
        return since, until
    now = datetime.now(timezone.utc)
    if window == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if window == "last_7d":
        return now - timedelta(days=7), now
    if window == "last_30d":
        return now - timedelta(days=30), now
    return since, until


@router.get("/contacts/{contact_id}/activity", response_model=ContactActivityOut)
def per_contact_activity(
    contact_id: int,
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> ContactActivityOut:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("Contact")
    organisation = db.get(Organisation, contact.organisation_id)

    order_clause = (
        (ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc())
        if order == "desc"
        else (ActivityEvent.occurred_at.asc(), ActivityEvent.id.asc())
    )
    events_stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.contact_id == contact_id)
        .order_by(*order_clause)
        .limit(limit)
        .offset(offset)
    )
    events = db.execute(events_stmt).scalars().all()

    total = db.execute(
        select(func.count())
        .select_from(ActivityEvent)
        .where(ActivityEvent.contact_id == contact_id)
    ).scalar_one()

    sent_messages, drafts = _hydrate_snapshots(db, events)
    items = [
        _serialise(
            ev,
            contact,
            organisation,
            _snapshot_for(ev, sent_messages, drafts),
        )
        for ev in events
    ]

    contact_ref = ContactRefWithOrg(
        id=contact.id,
        first_name=contact.first_name,
        last_name=contact.last_name,
        organisation=OrganisationRef(id=organisation.id, name=organisation.name)
        if organisation is not None
        else None,
    )
    return ContactActivityOut(items=items, total=total, contact=contact_ref)


@router.get("/activity", response_model=GlobalActivityOut)
def global_activity(
    db: Session = Depends(get_db),
    event_type: Annotated[list[ActivityEventType] | None, Query()] = None,
    contact_id: int | None = None,
    organisation_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    window: WindowPreset | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> GlobalActivityOut:
    try:
        filters = ActivityFilter(
            event_type=list(event_type or []),
            contact_id=contact_id,
            organisation_id=organisation_id,
            since=since,
            until=until,
            window=window,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as exc:
        raise api_error("validation_error", str(exc), 422) from exc

    since_eff, until_eff = _apply_window(filters.since, filters.until, filters.window)

    stmt = select(ActivityEvent)
    if filters.event_type:
        stmt = stmt.where(ActivityEvent.event_type.in_(filters.event_type))
    if filters.contact_id is not None:
        stmt = stmt.where(ActivityEvent.contact_id == filters.contact_id)
    if filters.organisation_id is not None:
        stmt = stmt.where(ActivityEvent.organisation_id == filters.organisation_id)
    if since_eff is not None:
        stmt = stmt.where(ActivityEvent.occurred_at >= since_eff)
    if until_eff is not None:
        stmt = stmt.where(ActivityEvent.occurred_at < until_eff)
    if filters.cursor is not None:
        cursor_ts, cursor_id = decode_cursor(filters.cursor)
        # Keyset predicate for (occurred_at DESC, id DESC): rows strictly older than (ts, id).
        stmt = stmt.where(
            or_(
                ActivityEvent.occurred_at < cursor_ts,
                and_(ActivityEvent.occurred_at == cursor_ts, ActivityEvent.id < cursor_id),
            )
        )

    stmt = stmt.order_by(ActivityEvent.occurred_at.desc(), ActivityEvent.id.desc()).limit(
        filters.limit + 1
    )
    rows = db.execute(stmt).scalars().all()

    has_more = len(rows) > filters.limit
    events = rows[: filters.limit]

    contacts, orgs = _hydrate_contacts(db, events)
    sent_messages, drafts = _hydrate_snapshots(db, events)
    items: list[ActivityEventView] = []
    for ev in events:
        contact = contacts.get(ev.contact_id)
        if contact is None:
            # The contact was deleted mid-query; skip its rows. FK cascade will normally
            # remove the event too, but a concurrent delete could momentarily race.
            continue
        org = orgs.get(ev.organisation_id)
        snapshot = _snapshot_for(ev, sent_messages, drafts)
        items.append(_serialise(ev, contact, org, snapshot))

    next_cursor: str | None = None
    if has_more and items:
        last = events[-1]
        next_cursor = encode_cursor(last.occurred_at, last.id)

    return GlobalActivityOut(items=items, next_cursor=next_cursor, has_more=has_more)
