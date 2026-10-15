"""Activity-event schemas (feature 002).

Payload shapes for each `ActivityEventType` are documented as `TypedDict`s so services that
call `record_event(..., payload=...)` have a reference. They are NOT enforced at runtime —
`activity_event.payload` is stored as raw JSONB (research.md R2).

The reader-side `ActivityEventView`, filter model, and cursor codec are consumed by the
per-contact endpoint (`GET /contacts/{id}/activity`, T017) and the global endpoint
(`GET /activity`, T036).
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, field_validator

from app.models.activity_event import ActivityActor, ActivityEventType

# ---------------------------------------------------------------------------
# Payload shape references (documentation only; not runtime-validated).
# ---------------------------------------------------------------------------


class LeadCreatedPayload(TypedDict, total=False):
    pass  # empty payload — contact reference on the row is enough


class EnrichmentAttemptedPayload(TypedDict, total=False):
    outcome: str  # "email_found" | "email_not_found" | "domain_not_found" | "error"
    reason: str | None
    hunter_confidence: float | None


class DraftGeneratedPayload(TypedDict, total=False):
    draft_id: int
    template_id: int
    template_name: str
    prompt_id: int


class DraftRegeneratedPayload(TypedDict, total=False):
    draft_id: int
    template_id: int
    template_name: str
    prompt_id: int
    previous_generated_at: str  # ISO-8601


class DraftStoredInMailboxPayload(TypedDict, total=False):
    draft_id: int
    folder_path: str
    mailbox_uid: int


class MailboxStoreFailedPayload(TypedDict, total=False):
    draft_id: int
    reason: str
    imap_error_code: str | None


class EmailSentPayload(TypedDict, total=False):
    sent_message_id: int
    template_id: int
    recipient: str


class SendFailedPayload(TypedDict, total=False):
    draft_id: int
    reason: str
    smtp_error_code: str | None


class TodoCreatedPayload(TypedDict, total=False):
    todo_id: int
    todo_type: str  # "send" | "follow_up" | "manual"
    due_at: str  # ISO-8601


class TodoCompletedPayload(TypedDict, total=False):
    todo_id: int
    completion_via: str  # "sent" | "mailbox_stored" | "manual"


class TodoCancelledPayload(TypedDict, total=False):
    todo_id: int
    reason: str  # "status_changed" | "draft_discarded" | "manual"


class FollowUpScheduledPayload(TypedDict, total=False):
    todo_id: int
    sent_message_id: int
    due_at: str  # ISO-8601


class StatusChangedPayload(TypedDict, total=False):
    from_: str  # ContactStatus value (renamed to avoid Python keyword collision at read time)
    to: str  # ContactStatus value


# ---------------------------------------------------------------------------
# Keyset pagination cursor codec (research.md R9). Used by the global Activity endpoint
# in Phase 5; provided here so both the endpoint and any tests share one implementation.
# The cursor is base64url-encoded JSON to keep it opaque in URLs.
# ---------------------------------------------------------------------------


def encode_cursor(occurred_at: datetime, id_: int) -> str:
    payload = json.dumps({"occurred_at": occurred_at.isoformat(), "id": id_}).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    padded = cursor + "=" * (-len(cursor) % 4)
    raw = base64.urlsafe_b64decode(padded.encode())
    data: dict[str, Any] = json.loads(raw)
    return datetime.fromisoformat(data["occurred_at"]), int(data["id"])


# ---------------------------------------------------------------------------
# Response view (per-contact + global endpoints, contracts/api.md § ActivityEventView).
# Every field is always present so the frontend renders one component; nulls are used for
# the optional `message_snapshot` join and the optional organisation reference (some events
# — like `lead_created` for a contact without an organisation — should still be very rare,
# but the schema tolerates it).
# ---------------------------------------------------------------------------


class ContactRef(BaseModel):
    id: int
    first_name: str
    last_name: str


class OrganisationRef(BaseModel):
    id: int
    name: str


class ContactRefWithOrg(ContactRef):
    organisation: OrganisationRef | None = None


class MessageSnapshot(BaseModel):
    subject: str
    body: str
    delivery_status: str | None = None


class ActivityEventView(BaseModel):
    id: int
    event_type: ActivityEventType
    actor: ActivityActor
    occurred_at: datetime
    contact: ContactRef
    organisation: OrganisationRef | None = None
    summary: str
    payload: dict[str, Any]
    message_snapshot: MessageSnapshot | None = None


class ContactActivityOut(BaseModel):
    items: list[ActivityEventView]
    total: int
    contact: ContactRefWithOrg


class GlobalActivityOut(BaseModel):
    items: list[ActivityEventView]
    next_cursor: str | None = None
    has_more: bool = False


# ---------------------------------------------------------------------------
# Query filter for the global endpoint (contracts/api.md § GET /api/v1/activity).
# FastAPI binds each field from a query parameter; `event_type` accepts repetition.
# ---------------------------------------------------------------------------


WindowPreset = Literal["today", "last_7d", "last_30d"]


class ActivityFilter(BaseModel):
    event_type: list[ActivityEventType] = Field(default_factory=list)
    contact_id: int | None = None
    organisation_id: int | None = None
    since: datetime | None = None
    until: datetime | None = None
    window: WindowPreset | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("cursor")
    @classmethod
    def _cursor_is_decodable(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            decode_cursor(v)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("cursor is not a valid activity keyset cursor") from exc
        return v
