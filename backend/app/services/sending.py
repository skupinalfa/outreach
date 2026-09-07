"""Send-todo execution service.

Composes the MIME multipart (plaintext + HTML, HTML template mirrors the newcon signature
block from `outreach/cold_email_pipeline.py::create_draft`), calls the SMTP boundary, records
a `SentMessage`, marks the todo `done`, and moves the contact to `contacted` (if enriched).
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.integrations import smtp as smtp_integration
from app.logging import get_logger
from app.models.contact import Contact, ContactStatus
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.settings import Settings as SettingsRow
from app.models.todo import Todo, TodoStatus, TodoType
from app.security import secrets as secret_helpers

log = get_logger("sending")


_HTML_FOOTER = """
<div style="font-family: -apple-system, BlinkMacSystemFont, helvetica, sans-serif;">
  <p style="font-size: 12pt; margin-bottom: 4px;"><strong>newcon GmbH</strong></p>
  <p style="font-size: 8pt; margin: 0;"><a href="http://www.newcon.info">www.newcon.info</a></p>
  <p style="font-size: 8pt; margin: 0;"><a href="mailto:kontakt@newcon.info">kontakt@newcon.info</a></p>
  <p style="font-size: 8pt; margin: 8px 0 0 0;">Schießrain 32, 77652 Offenburg &middot; T +49 1577 9472074</p>
</div>
"""


class SendingError(Exception):
    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _load_smtp_config(db: Session) -> tuple[SettingsRow, str, str]:
    settings = db.get(SettingsRow, 1)
    if settings is None:
        raise SendingError("credential_not_set", "SMTP settings not configured.", status=400)
    if not settings.smtp_host or not settings.smtp_port:
        raise SendingError(
            "credential_not_set", "SMTP host/port not configured.", status=400
        )
    if settings.smtp_username_ct is None or settings.smtp_password_ct is None:
        raise SendingError(
            "credential_not_set", "SMTP credentials not configured.", status=400
        )
    if not settings.sender_email:
        raise SendingError(
            "credential_not_set", "Sender email not configured.", status=400
        )
    return (
        settings,
        secret_helpers.decrypt(settings.smtp_username_ct),
        secret_helpers.decrypt(settings.smtp_password_ct),
    )


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


def send_todo(
    db: Session,
    todo_id: int,
    subject_override: str,
    body_override: str,
) -> SentMessage:
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise SendingError("not_found", "Todo does not exist.", status=404)
    if todo.type != TodoType.SEND:
        raise SendingError(
            "conflict", "Only send todos can be sent.", status=409
        )
    if todo.status == TodoStatus.DONE:
        raise SendingError("conflict", "Todo already sent.", status=409)

    contact = db.get(Contact, todo.contact_id)
    if contact is None or not contact.email:
        raise SendingError(
            "conflict", "Contact is missing an email address.", status=409
        )

    settings, username, password = _load_smtp_config(db)
    message = _build_message(
        from_display=settings.sender_display_name,
        from_email=settings.sender_email,
        to_email=contact.email,
        subject=subject_override,
        body=body_override,
    )

    try:
        smtp_integration.send(
            message,
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=username,
            password=password,
        )
    except smtp_integration.SmtpCredentialError as exc:
        raise SendingError("credential_not_set", str(exc), status=400) from exc
    except smtp_integration.SmtpError as exc:
        raise SendingError("smtp_error", str(exc)) from exc

    sent = SentMessage(
        contact_id=contact.id,
        subject=subject_override,
        body=body_override,
        delivery_status=DeliveryStatus.SENT.value,
    )
    db.add(sent)
    db.flush()

    todo.status = TodoStatus.DONE
    todo.completed_at = datetime.now(UTC)
    todo.sent_message_id = sent.id

    if contact.status == ContactStatus.ENRICHED:
        contact.status = ContactStatus.CONTACTED

    return sent
