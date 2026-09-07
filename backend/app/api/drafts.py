from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import api_error, not_found
from app.db import get_db
from app.models.activity_event import ActivityActor, ActivityEventType
from app.models.contact import Contact
from app.models.draft import Draft
from app.models.todo import Todo, TodoStatus, TodoType
from app.schemas.draft import DraftIn, DraftOut, DraftPatch
from app.security.auth import require_auth
from app.services import activity as activity_service
from app.services.generation import GenerationError, generate_draft

router = APIRouter(tags=["drafts"], dependencies=[Depends(require_auth)])


@router.post(
    "/contacts/{contact_id}/drafts",
    response_model=DraftOut,
    status_code=status.HTTP_201_CREATED,
)
def create_draft(contact_id: int, body: DraftIn, db: Session = Depends(get_db)) -> Draft:
    try:
        return generate_draft(db, contact_id, body.template_id)
    except GenerationError as exc:
        # FR-029 audit-persistence — same rationale as enrich.
        db.commit()
        raise api_error(exc.code, exc.message, exc.status) from exc


@router.get("/contacts/{contact_id}/draft", response_model=DraftOut)
def get_draft(contact_id: int, db: Session = Depends(get_db)) -> Draft:
    draft = db.execute(select(Draft).where(Draft.contact_id == contact_id)).scalar_one_or_none()
    if draft is None:
        raise not_found("Draft")
    return draft


@router.patch("/contacts/{contact_id}/draft", response_model=DraftOut)
def patch_draft(contact_id: int, body: DraftPatch, db: Session = Depends(get_db)) -> Draft:
    draft = db.execute(select(Draft).where(Draft.contact_id == contact_id)).scalar_one_or_none()
    if draft is None:
        raise not_found("Draft")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(draft, field, value)
    return draft


@router.delete("/contacts/{contact_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft(contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("Contact")
    draft = db.execute(select(Draft).where(Draft.contact_id == contact_id)).scalar_one_or_none()
    if draft is None:
        return
    open_send_todos = db.execute(
        select(Todo).where(
            Todo.contact_id == contact_id,
            Todo.type == TodoType.SEND,
            Todo.status.in_([TodoStatus.OPEN, TodoStatus.SCHEDULED]),
        )
    ).scalars().all()
    for todo in open_send_todos:
        todo.status = TodoStatus.CANCELLED
        # completed_via left NULL — the reason lives on the activity event (data-model.md).
        activity_service.record_event(
            db,
            contact_id=contact.id,
            organisation_id=contact.organisation_id,
            event_type=ActivityEventType.TODO_CANCELLED,
            actor=ActivityActor.OPERATOR,
            payload={"todo_id": todo.id, "reason": "draft_discarded"},
        )
    db.delete(draft)
