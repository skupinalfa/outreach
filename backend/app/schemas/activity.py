"""Activity-event schemas (feature 002).

This module is intentionally partial in this milestone: only the pieces exercised by the
Phase-2 write path and the Phase-6 cascade tests are implemented. The reader-side response
schema (`ActivityEventView`) and the query-filter model live here too but are populated when
the corresponding API endpoints land in Phase 3 (`GET /contacts/{id}/activity`) and Phase 5
(`GET /activity`). Adding them now would be dead code until then (Constitution I).

Payload shapes for each `ActivityEventType` are documented as `TypedDict`s so services that
call `record_event(..., payload=...)` have a reference. They are NOT enforced at runtime —
`activity_event.payload` is stored as raw JSONB (research.md R2).
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, TypedDict

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
