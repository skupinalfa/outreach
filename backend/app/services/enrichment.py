"""Enrichment service — orchestrates Hunter calls and persists the outcome on the contact.

FR-005 / FR-006 / FR-006a / FR-029:
- Success: refreshes `organisation.domain` if empty, refreshes `contact.position` if empty,
  refreshes `last_enriched_at`, clears `last_enrichment_error`, and moves status
  `new` → `enriched` when an email is available.
- Email is written **only when currently None** (FR-005 no-overwrite): if the operator has
  already set an email (manually or via a previous enrichment), it survives re-enrichment.
  To replace a Hunter-found email via a fresh lookup, the operator must first clear the
  field by hand on the contact detail (FR-006a) and re-run enrichment.
- Failure: sets `last_enriched_at` and stores the error string in `last_enrichment_error`
  in the same transaction (durable audit).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.integrations import hunter
from app.logging import get_logger
from app.models.activity_event import ActivityActor, ActivityEventType
from app.models.contact import Contact, ContactStatus
from app.models.organisation import Organisation
from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers
from app.services import activity as activity_service

log = get_logger("enrichment")


class EnrichmentError(Exception):
    """Wrapper for enrichment orchestration failures the API layer catches."""

    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _hunter_api_key(db: Session) -> str:
    settings = db.get(SettingsRow, 1)
    if settings is None or settings.hunter_api_key_ct is None:
        raise EnrichmentError(
            "credential_not_set",
            "Hunter API key is not configured. Set it in Settings.",
            status=400,
        )
    return secret_helpers.decrypt(settings.hunter_api_key_ct)


def enrich_contact(db: Session, contact_id: int) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise EnrichmentError("not_found", "Contact does not exist.", status=404)

    org = db.get(Organisation, contact.organisation_id)
    if org is None:
        raise EnrichmentError("not_found", "Contact has no organisation.", status=404)

    api_key = _hunter_api_key(db)

    try:
        domain = org.domain or hunter.resolve_domain(org.name, api_key)
        if not domain:
            reason = "Hunter could not resolve a domain for this company."
            _record_error(contact, reason)
            _record_activity(db, contact, outcome="domain_not_found", reason=reason)
            return contact
        if not org.domain:
            org.domain = domain

        result = hunter.find_email(contact.first_name, contact.last_name, domain, api_key)
    except hunter.HunterCredentialError as exc:
        _record_error(contact, str(exc))
        _record_activity(db, contact, outcome="error", reason=str(exc))
        raise EnrichmentError("credential_not_set", str(exc), status=400) from exc
    except hunter.HunterError as exc:
        _record_error(contact, str(exc))
        _record_activity(db, contact, outcome="error", reason=str(exc))
        raise EnrichmentError("hunter_error", str(exc)) from exc

    contact.last_enriched_at = datetime.now(UTC)
    contact.last_enrichment_error = None
    if result.email:
        # FR-005: don't overwrite an existing email — that value could be a manual
        # correction the operator made. The other enrichment outputs still update.
        if contact.email is None:
            contact.email = result.email
        if contact.position is None and result.position:
            contact.position = result.position
        # A contact with any email (manual or freshly enriched) is actionable and moves out
        # of "new" — this keeps the state machine consistent with the send-flow gate.
        status_transition: tuple[ContactStatus, ContactStatus] | None = None
        if contact.status == ContactStatus.NEW and contact.email:
            status_transition = (contact.status, ContactStatus.ENRICHED)
            contact.status = ContactStatus.ENRICHED
        _record_activity(
            db,
            contact,
            outcome="email_found",
            hunter_confidence=result.score,
        )
        if status_transition is not None:
            _record_status_change(db, contact, *status_transition)
    else:
        contact.last_enrichment_error = "Hunter found no email for this contact."
        _record_activity(
            db,
            contact,
            outcome="email_not_found",
            reason=contact.last_enrichment_error,
        )
    return contact


def _record_activity(
    db: Session,
    contact: Contact,
    *,
    outcome: str,
    reason: str | None = None,
    hunter_confidence: int | None = None,
) -> None:
    payload: dict[str, object] = {"outcome": outcome, "reason": reason}
    if hunter_confidence is not None:
        payload["hunter_confidence"] = hunter_confidence
    activity_service.record_event(
        db,
        contact_id=contact.id,
        organisation_id=contact.organisation_id,
        event_type=ActivityEventType.ENRICHMENT_ATTEMPTED,
        actor=ActivityActor.OPERATOR,
        payload=payload,
    )


def _record_status_change(
    db: Session, contact: Contact, from_status: ContactStatus, to_status: ContactStatus
) -> None:
    activity_service.record_event(
        db,
        contact_id=contact.id,
        organisation_id=contact.organisation_id,
        event_type=ActivityEventType.STATUS_CHANGED,
        actor=ActivityActor.SYSTEM,
        payload={"from": from_status.value, "to": to_status.value},
    )


def _record_error(contact: Contact, message: str) -> None:
    contact.last_enriched_at = datetime.now(UTC)
    contact.last_enrichment_error = message
