"""Save-to-mailbox orchestration (US3, FR-045..FR-049).

Snapshots the current draft, resolves the IMAP Drafts folder, APPENDs the message, records
the outcome activity event, and completes the todo — all in one DB transaction. Does NOT
call the follow-up scheduler (FR-048).
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import imap as imap_integration
from app.integrations.imap import (
    ImapConnectSettings,
    IMAPCredentialError,
    IMAPDraftsNotFoundError,
    IMAPError,
    IMAPStoreConflictError,
)
from app.logging import get_logger
from app.models.activity_event import ActivityActor, ActivityEventType
from app.models.contact import Contact
from app.models.draft import Draft
from app.models.settings import Settings as SettingsRow
from app.models.todo import Todo, TodoStatus, TodoType
from app.security import secrets as secret_helpers
from app.services import activity as activity_service

log = get_logger("mailbox_drafts")


class MailboxSaveError(Exception):
    """Wrapper the API layer catches; carries a stable `code` for the error envelope."""

    def __init__(self, code: str, message: str, status: int = 502, detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail or {}


class SaveResult:
    def __init__(
        self,
        todo: Todo,
        draft: Draft,
        folder: str,
        uid: int | None,
        stored_at: datetime,
        replaced_previous: bool,
    ) -> None:
        self.todo = todo
        self.draft = draft
        self.folder = folder
        self.uid = uid
        self.stored_at = stored_at
        self.replaced_previous = replaced_previous


def save_to_mailbox(
    db: Session,
    todo_id: int,
    subject_override: str,
    body_override: str,
) -> SaveResult:
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise MailboxSaveError("not_found", "Todo does not exist.", status=404)
    if todo.type != TodoType.SEND:
        raise MailboxSaveError(
            "todo_not_actionable", "Only send todos can be saved to the mailbox.", status=409
        )
    if todo.status not in (TodoStatus.SCHEDULED, TodoStatus.OPEN):
        raise MailboxSaveError(
            "todo_not_actionable", "Todo is not open — cannot save to mailbox.", status=409
        )

    contact = db.get(Contact, todo.contact_id)
    if contact is None or not contact.email:
        raise MailboxSaveError(
            "conflict", "Contact is missing an email address.", status=409
        )

    draft = db.execute(select(Draft).where(Draft.contact_id == contact.id)).scalar_one_or_none()
    if draft is None:
        raise MailboxSaveError(
            "conflict", "No draft exists for this contact.", status=409
        )

    settings = db.get(SettingsRow, 1)
    cfg = _imap_settings(settings)
    if not settings.sender_email:
        raise MailboxSaveError(
            "credential_not_set", "Sender email not configured.", status=400
        )

    # Apply the operator's edits before snapshotting — the mailbox copy MUST match what the
    # operator saw on-screen (FR-046 step 1).
    draft.subject = subject_override
    draft.body = body_override
    db.flush()

    msg = _build_message(
        from_display=settings.sender_display_name,
        from_email=settings.sender_email,
        to_email=contact.email,
        subject=subject_override,
        body=body_override,
    )

    previous_uid = draft.mailbox_uid
    previous_folder = draft.mailbox_folder

    try:
        with imap_integration.connect(cfg) as conn:
            folder, is_new_detection = imap_integration.resolve_drafts_folder(
                conn,
                operator_override=settings.imap_drafts_folder,
                detected_cache=settings.imap_drafts_folder_detected,
            )

            replaced = False
            if previous_uid is not None and previous_folder == folder:
                try:
                    imap_integration.replace_previous(conn, folder, previous_uid)
                    replaced = True
                except IMAPStoreConflictError:
                    # Fallback path per FR-049 for non-UIDPLUS servers.
                    raise
                except IMAPError:
                    # If the previous copy is already gone, treat it as no-op and proceed
                    # with the new APPEND — the invariant "no duplicates" still holds because
                    # only the new copy will exist afterwards.
                    replaced = False

            uid = imap_integration.append_draft(conn, folder, msg)

            if is_new_detection and folder != settings.imap_drafts_folder_detected:
                settings.imap_drafts_folder_detected = folder

    except IMAPCredentialError as exc:
        _record_failure(db, contact, draft, str(exc), imap_error_code=None)
        raise MailboxSaveError("credential_not_set", str(exc), status=400) from exc
    except IMAPDraftsNotFoundError as exc:
        _record_failure(db, contact, draft, str(exc), imap_error_code="drafts_not_found")
        raise MailboxSaveError(
            "imap_drafts_not_found",
            str(exc),
            status=502,
            detail={"tried_folders": ["Drafts", "[Gmail]/Drafts", "INBOX.Drafts"]},
        ) from exc
    except IMAPStoreConflictError as exc:
        _record_failure(db, contact, draft, str(exc), imap_error_code="store_conflict")
        raise MailboxSaveError(
            "mailbox_store_conflict",
            str(exc),
            status=409,
            detail={
                "folder": previous_folder,
                "previous_stored_at": draft.mailbox_stored_at.isoformat()
                if draft.mailbox_stored_at
                else None,
            },
        ) from exc
    except IMAPError as exc:
        _record_failure(db, contact, draft, str(exc), imap_error_code=None)
        raise MailboxSaveError("imap_error", str(exc), status=502) from exc

    stored_at = datetime.now(UTC)
    draft.mailbox_folder = folder
    draft.mailbox_uid = uid
    draft.mailbox_stored_at = stored_at

    todo.status = TodoStatus.DONE
    todo.completed_at = stored_at
    todo.completed_via = "mailbox_stored"

    activity_service.record_event(
        db,
        contact_id=contact.id,
        organisation_id=contact.organisation_id,
        event_type=ActivityEventType.DRAFT_STORED_IN_MAILBOX,
        actor=ActivityActor.OPERATOR,
        payload={"draft_id": draft.id, "folder_path": folder, "mailbox_uid": uid},
    )
    activity_service.record_event(
        db,
        contact_id=contact.id,
        organisation_id=contact.organisation_id,
        event_type=ActivityEventType.TODO_COMPLETED,
        actor=ActivityActor.OPERATOR,
        payload={"todo_id": todo.id, "completion_via": "mailbox_stored"},
    )

    return SaveResult(
        todo=todo,
        draft=draft,
        folder=folder,
        uid=uid,
        stored_at=stored_at,
        replaced_previous=replaced,
    )


# ---------------------------------------------------------------------------


def _imap_settings(settings: SettingsRow | None) -> ImapConnectSettings:
    if settings is None:
        raise MailboxSaveError("credential_not_set", "Settings row missing.", status=400)
    if not settings.imap_host or not settings.imap_port:
        raise MailboxSaveError(
            "credential_not_set", "IMAP host/port not configured.", status=400
        )
    if settings.imap_username_ct is None or settings.imap_password_ct is None:
        raise MailboxSaveError(
            "credential_not_set", "IMAP credentials not configured.", status=400
        )
    return ImapConnectSettings(
        host=settings.imap_host,
        port=settings.imap_port,
        username=secret_helpers.decrypt(settings.imap_username_ct),
        password=secret_helpers.decrypt(settings.imap_password_ct),
        use_tls=settings.imap_use_tls,
    )


_HTML_FOOTER = """
<div style="font-family: -apple-system, BlinkMacSystemFont, helvetica, sans-serif;">
  <p style="font-size: 12pt; margin-bottom: 4px;"><strong>newcon GmbH</strong></p>
  <p style="font-size: 8pt; margin: 0;"><a href="http://www.newcon.info">www.newcon.info</a></p>
  <p style="font-size: 8pt; margin: 0;"><a href="mailto:kontakt@newcon.info">kontakt@newcon.info</a></p>
  <p style="font-size: 8pt; margin: 8px 0 0 0;">Schie&szlig;rain 32, 77652 Offenburg &middot; T +49 1577 9472074</p>
</div>
"""


def _build_message(
    from_display: str | None,
    from_email: str,
    to_email: str,
    subject: str,
    body: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_display} <{from_email}>" if from_display else from_email
    msg["To"] = to_email
    msg.set_content(body)
    html_body = "<p>" + body.replace("\n", "<br>") + "</p>" + _HTML_FOOTER
    msg.add_alternative(f"<html><body>{html_body}</body></html>", subtype="html")
    return msg


def _record_failure(
    db: Session,
    contact: Contact,
    draft: Draft,
    reason: str,
    imap_error_code: str | None,
) -> None:
    activity_service.record_event(
        db,
        contact_id=contact.id,
        organisation_id=contact.organisation_id,
        event_type=ActivityEventType.MAILBOX_STORE_FAILED,
        actor=ActivityActor.OPERATOR,
        payload={"draft_id": draft.id, "reason": reason, "imap_error_code": imap_error_code},
    )
