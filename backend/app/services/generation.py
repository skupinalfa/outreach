"""Draft generation — loads the active prompt + chosen template + contact, builds the prompt,
calls OpenAI, parses the response, upserts the Draft, and creates or refreshes the `send` todo
in the same transaction (FR-010).

Snapshotting: `template_body_snapshot` and `prompt_text_snapshot` are stored on the draft so
that later edits to the template or prompt do not retroactively change the draft's provenance.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import openai_client
from app.logging import get_logger
from app.models.activity_event import ActivityActor, ActivityEventType
from app.models.contact import Contact
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.settings import Settings as SettingsRow
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType
from app.security import secrets as secret_helpers
from app.services import activity as activity_service
from app.services.openai_parser import OpenAIParseError, parse_openai_response
from app.services.prompt_builder import (
    ContactContext,
    PromptTemplateError,
    build_prompt,
)

log = get_logger("generation")


class GenerationError(Exception):
    def __init__(self, code: str, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _openai_credentials(db: Session) -> tuple[str, str]:
    settings = db.get(SettingsRow, 1)
    if settings is None or settings.openai_api_key_ct is None:
        raise GenerationError(
            "credential_not_set",
            "OpenAI API key is not configured. Set it in Settings.",
            status=400,
        )
    return secret_helpers.decrypt(settings.openai_api_key_ct), settings.openai_model


def _active_prompt(db: Session) -> Prompt:
    prompt = db.execute(select(Prompt).where(Prompt.is_active.is_(True))).scalar_one_or_none()
    if prompt is None:
        raise GenerationError(
            "template_missing",
            "No active prompt is configured. Set one under Prompts.",
            status=409,
        )
    return prompt


def _template(db: Session, template_id: int) -> Template:
    template = db.get(Template, template_id)
    if template is None or template.is_archived:
        raise GenerationError("template_missing", "Template does not exist.", status=409)
    return template


def _upsert_send_todo(db: Session, contact: Contact, draft: Draft, org: Organisation) -> None:
    """FR-010 — every draft has an open `send` todo. Regeneration refreshes the existing one."""
    existing = db.execute(
        select(Todo).where(
            Todo.contact_id == contact.id,
            Todo.type == TodoType.SEND,
            Todo.status.in_([TodoStatus.OPEN, TodoStatus.SCHEDULED]),
        )
    ).scalar_one_or_none()

    title = f"Send email to {contact.first_name} {contact.last_name} ({org.name})"
    if existing is None:
        due_at = datetime.now(UTC)
        todo = Todo(
            type=TodoType.SEND,
            title=title,
            contact_id=contact.id,
            draft_id=draft.id,
            due_at=due_at,
            status=TodoStatus.OPEN,
        )
        db.add(todo)
        db.flush()
        activity_service.record_event(
            db,
            contact_id=contact.id,
            organisation_id=contact.organisation_id,
            event_type=ActivityEventType.TODO_CREATED,
            actor=ActivityActor.SYSTEM,
            payload={
                "todo_id": todo.id,
                "todo_type": TodoType.SEND.value,
                "due_at": due_at.isoformat(),
            },
        )
    else:
        existing.title = title
        existing.draft_id = draft.id
        existing.status = TodoStatus.OPEN


def generate_draft(db: Session, contact_id: int, template_id: int) -> Draft:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise GenerationError("not_found", "Contact does not exist.", status=404)

    org = db.get(Organisation, contact.organisation_id)
    if org is None or not org.domain:
        raise GenerationError(
            "conflict",
            "Enrich the contact (or set the organisation domain) before generating a draft.",
            status=409,
        )

    template = _template(db, template_id)
    prompt_row = _active_prompt(db)
    api_key, model = _openai_credentials(db)

    try:
        prompt_text = build_prompt(
            prompt_row.text,
            ContactContext(
                domain=org.domain,
                last_name=contact.last_name,
                gender=contact.gender,
            ),
            template.body,
        )
    except PromptTemplateError as exc:
        raise GenerationError("validation_error", str(exc), status=422) from exc

    try:
        raw = openai_client.generate(prompt_text, api_key, model=model)
        subject, body = parse_openai_response(raw)
    except openai_client.OpenAICredentialError as exc:
        _record_failure(contact, str(exc))
        raise GenerationError("credential_not_set", str(exc), status=400) from exc
    except openai_client.OpenAIError as exc:
        _record_failure(contact, str(exc))
        raise GenerationError("openai_error", str(exc)) from exc
    except OpenAIParseError as exc:
        _record_failure(contact, str(exc))
        raise GenerationError("openai_parse_error", str(exc)) from exc

    existing = db.execute(select(Draft).where(Draft.contact_id == contact.id)).scalar_one_or_none()
    previous_generated_at: datetime | None = None
    if existing is None:
        draft = Draft(
            contact_id=contact.id,
            template_id=template.id,
            template_body_snapshot=template.body,
            prompt_id=prompt_row.id,
            prompt_text_snapshot=prompt_row.text,
            subject=subject,
            body=body,
        )
        db.add(draft)
    else:
        previous_generated_at = existing.generated_at
        existing.template_id = template.id
        existing.template_body_snapshot = template.body
        existing.prompt_id = prompt_row.id
        existing.prompt_text_snapshot = prompt_row.text
        existing.subject = subject
        existing.body = body
        existing.generated_at = datetime.now(UTC)
        # A fresh draft version invalidates the mailbox coordinate of the previous version
        # (FR-046 replace-in-place is per-draft-version — research.md R6).
        existing.mailbox_folder = None
        existing.mailbox_uid = None
        existing.mailbox_stored_at = None
        draft = existing

    db.flush()

    contact.last_generated_at = datetime.now(UTC)
    contact.last_generation_error = None

    payload: dict[str, object] = {
        "draft_id": draft.id,
        "template_id": template.id,
        "template_name": template.name,
        "prompt_id": prompt_row.id,
    }
    if previous_generated_at is None:
        event_type = ActivityEventType.DRAFT_GENERATED
    else:
        event_type = ActivityEventType.DRAFT_REGENERATED
        payload["previous_generated_at"] = previous_generated_at.isoformat()
    activity_service.record_event(
        db,
        contact_id=contact.id,
        organisation_id=contact.organisation_id,
        event_type=event_type,
        actor=ActivityActor.OPERATOR,
        payload=payload,
    )

    _upsert_send_todo(db, contact, draft, org)
    return draft


def _record_failure(contact: Contact, message: str) -> None:
    contact.last_generated_at = datetime.now(UTC)
    contact.last_generation_error = message
