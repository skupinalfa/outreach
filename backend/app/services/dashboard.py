"""Dashboard overview — one function issues the aggregate queries from data-model.md.

Design:
- On empty DB (no contacts) OR unset master password, returns the onboarding shape and omits
  the numeric fields — the UI renders a guided empty state (FR-035).
- "Due today" is bounded by the operator's local midnight-to-midnight in Settings.timezone,
  so evening todos don't slip into "tomorrow" for a Berlin operator staring at UTC.
- Deltas compare the current window with the immediately-prior window of the same length.
- Follow-up-due count for the activity window counts follow-up todos whose `due_at` falls
  inside the window (not creation time) — that's what the operator actually cares about.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.settings import Settings as SettingsRow
from app.models.todo import Todo, TodoStatus, TodoType


@dataclass(frozen=True)
class _Window:
    start: datetime
    end: datetime  # exclusive


def _window(now: datetime, days: int) -> _Window:
    return _Window(start=now - timedelta(days=days), end=now)


def _prior_window(now: datetime, days: int) -> _Window:
    return _Window(start=now - timedelta(days=days * 2), end=now - timedelta(days=days))


def _count_contacts(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Contact)).scalar_one()


def _onboarding_required(db: Session) -> bool:
    settings = db.get(SettingsRow, 1)
    if settings is None or settings.master_password_hash is None:
        return True
    return _count_contacts(db) == 0


def _today_bounds_utc(tz_name: str, now: datetime) -> tuple[datetime, datetime]:
    """Return [midnight, next-midnight) in the operator's timezone, expressed in UTC."""
    tz = ZoneInfo(tz_name)
    local = now.astimezone(tz)
    start_local = datetime.combine(local.date(), datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _activity_counts(db: Session, window: _Window) -> dict[str, int]:
    leads = db.execute(
        select(func.count())
        .select_from(Contact)
        .where(Contact.created_at >= window.start, Contact.created_at < window.end)
    ).scalar_one()

    drafts = db.execute(
        select(func.count())
        .select_from(Draft)
        .where(Draft.generated_at >= window.start, Draft.generated_at < window.end)
    ).scalar_one()

    emails = db.execute(
        select(func.count())
        .select_from(SentMessage)
        .where(
            SentMessage.sent_at >= window.start,
            SentMessage.sent_at < window.end,
            SentMessage.delivery_status == DeliveryStatus.SENT.value,
        )
    ).scalar_one()

    follow_ups_due = db.execute(
        select(func.count())
        .select_from(Todo)
        .where(
            Todo.type == TodoType.FOLLOW_UP,
            Todo.due_at >= window.start,
            Todo.due_at < window.end,
        )
    ).scalar_one()

    replies = db.execute(
        select(func.count())
        .select_from(Contact)
        .where(
            Contact.status == ContactStatus.REPLIED,
            Contact.updated_at >= window.start,
            Contact.updated_at < window.end,
        )
    ).scalar_one()

    return {
        "leads_added": leads,
        "drafts_generated": drafts,
        "emails_sent": emails,
        "follow_ups_due": follow_ups_due,
        "replies_logged": replies,
    }


def _activity_block(db: Session, now: datetime, days: int) -> dict[str, Any]:
    current = _activity_counts(db, _window(now, days))
    prior = _activity_counts(db, _prior_window(now, days))
    delta = {key: current[key] - prior[key] for key in current}
    return {"window_days": days, **current, "delta_vs_prior": delta}


def _todos_block(db: Session, now: datetime, tz_name: str) -> dict[str, Any]:
    day_start, day_end = _today_bounds_utc(tz_name, now)

    overdue = db.execute(
        select(func.count())
        .select_from(Todo)
        .where(
            Todo.status.in_([TodoStatus.SCHEDULED, TodoStatus.OPEN]),
            Todo.due_at < now,
        )
    ).scalar_one()

    due_today = db.execute(
        select(func.count())
        .select_from(Todo)
        .where(
            Todo.status.in_([TodoStatus.SCHEDULED, TodoStatus.OPEN]),
            Todo.due_at >= day_start,
            Todo.due_at < day_end,
        )
    ).scalar_one()

    next_todo = db.execute(
        select(Todo)
        .where(Todo.status.in_([TodoStatus.SCHEDULED, TodoStatus.OPEN]))
        .order_by(Todo.due_at.asc())
        .limit(1)
    ).scalar_one_or_none()

    next_action: dict[str, Any] | None = None
    if next_todo is not None:
        next_action = {
            "todo_id": next_todo.id,
            "title": next_todo.title,
            "due_at": next_todo.due_at.isoformat(),
        }
    return {"overdue_count": overdue, "due_today_count": due_today, "next_action": next_action}


def _funnel_30d(db: Session, now: datetime) -> dict[str, Any]:
    window = _window(now, 30)
    sent = db.execute(
        select(func.count())
        .select_from(SentMessage)
        .where(
            SentMessage.sent_at >= window.start,
            SentMessage.sent_at < window.end,
            SentMessage.delivery_status == DeliveryStatus.SENT.value,
        )
    ).scalar_one()
    replied = db.execute(
        select(func.count())
        .select_from(Contact)
        .where(
            Contact.status == ContactStatus.REPLIED,
            Contact.updated_at >= window.start,
            Contact.updated_at < window.end,
        )
    ).scalar_one()
    meeting_booked = db.execute(
        select(func.count())
        .select_from(Contact)
        .where(
            Contact.status == ContactStatus.MEETING_BOOKED,
            Contact.updated_at >= window.start,
            Contact.updated_at < window.end,
        )
    ).scalar_one()
    return {
        "sent": sent,
        "replied": replied,
        "meeting_booked": meeting_booked,
        "reply_rate": (replied / sent) if sent else 0.0,
        "booking_rate": (meeting_booked / sent) if sent else 0.0,
    }


def build_overview(db: Session, timezone_name: str | None = None) -> dict[str, Any]:
    if _onboarding_required(db):
        return {"onboarding_required": True}

    settings = db.get(SettingsRow, 1)
    tz_name = timezone_name or (settings.timezone if settings else "Europe/Berlin")
    now = datetime.now(UTC)

    return {
        "onboarding_required": False,
        "todos": _todos_block(db, now, tz_name),
        "activity": _activity_block(db, now, 7),
        "activity_30d": _activity_block(db, now, 30),
        "funnel_30d": _funnel_30d(db, now),
    }
