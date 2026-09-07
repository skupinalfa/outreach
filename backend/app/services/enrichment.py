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
from app.models.contact import Contact, ContactStatus
from app.models.organisation import Organisation
from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers

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
            _record_error(contact, "Hunter could not resolve a domain for this company.")
            return contact
        if not org.domain:
            org.domain = domain

        result = hunter.find_email(contact.first_name, contact.last_name, domain, api_key)
    except hunter.HunterCredentialError as exc:
        _record_error(contact, str(exc))
        raise EnrichmentError("credential_not_set", str(exc), status=400) from exc
    except hunter.HunterError as exc:
        _record_error(contact, str(exc))
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
        if contact.status == ContactStatus.NEW and contact.email:
            contact.status = ContactStatus.ENRICHED
    else:
        contact.last_enrichment_error = "Hunter found no email for this contact."
    return contact


def _record_error(contact: Contact, message: str) -> None:
    contact.last_enriched_at = datetime.now(UTC)
    contact.last_enrichment_error = message
