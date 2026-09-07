from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import api_error, conflict, not_found
from app.db import get_db
from app.models.contact import Contact
from app.models.todo import Todo, TodoStatus, TodoType
from app.schemas.base import PaginatedOut
from app.schemas.todo import SentMessageOut, TodoIn, TodoOut, TodoPatch, TodoSendIn
from app.security.auth import require_auth
from app.services.sending import SendingError, send_todo
from app.services.todo_promotion import promote_scheduled_todos

router = APIRouter(
    prefix="/todos",
    tags=["todos"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=PaginatedOut[TodoOut])
def list_todos(
    db: Session = Depends(get_db),
    status_: Annotated[TodoStatus | None, Query(alias="status")] = None,
    type_: Annotated[TodoType | None, Query(alias="type")] = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedOut[TodoOut]:
    promote_scheduled_todos(db)

    query = select(Todo)
    count_q = select(func.count()).select_from(Todo)
    if status_ is not None:
        query = query.where(Todo.status == status_)
        count_q = count_q.where(Todo.status == status_)
    if type_ is not None:
        query = query.where(Todo.type == type_)
        count_q = count_q.where(Todo.type == type_)
    if due_before is not None:
        query = query.where(Todo.due_at < due_before)
        count_q = count_q.where(Todo.due_at < due_before)
    if due_after is not None:
        query = query.where(Todo.due_at >= due_after)
        count_q = count_q.where(Todo.due_at >= due_after)

    query = query.order_by(Todo.due_at.asc()).limit(limit).offset(offset)
    items = db.execute(query).scalars().all()
    total = db.execute(count_q).scalar_one()
    return PaginatedOut(items=[TodoOut.model_validate(t) for t in items], total=total)


@router.get("/{todo_id}", response_model=TodoOut)
def get_one(todo_id: int, db: Session = Depends(get_db)) -> Todo:
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise not_found("Todo")
    return todo


@router.post("", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
def create(body: TodoIn, db: Session = Depends(get_db)) -> Todo:
    if body.type != TodoType.MANUAL:
        raise conflict("Only manual todos can be created directly. System todos are generated.")
    if db.get(Contact, body.contact_id) is None:
        raise not_found("Contact")
    todo = Todo(
        type=body.type,
        title=body.title,
        contact_id=body.contact_id,
        due_at=body.due_at,
        status=TodoStatus.OPEN,
    )
    db.add(todo)
    db.flush()
    return todo


@router.patch("/{todo_id}", response_model=TodoOut)
def patch(todo_id: int, body: TodoPatch, db: Session = Depends(get_db)) -> Todo:
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise not_found("Todo")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(todo, field, value)
    if body.status == TodoStatus.DONE and todo.completed_at is None:
        todo.completed_at = datetime.utcnow()
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(todo_id: int, db: Session = Depends(get_db)):
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise not_found("Todo")
    if todo.type != TodoType.MANUAL:
        raise conflict("Only manual todos can be deleted. Cancel system todos via status change.")
    db.delete(todo)


@router.post("/{todo_id}/send", response_model=SentMessageOut, status_code=status.HTTP_201_CREATED)
def send(todo_id: int, body: TodoSendIn, db: Session = Depends(get_db)) -> SentMessageOut:
    try:
        sent = send_todo(db, todo_id, body.subject, body.body)
    except SendingError as exc:
        # Persist the send_failed activity event recorded inside the service before the
        # exception bubbles up (mirrors the enrich handler's pattern for audit fields).
        db.commit()
        raise api_error(exc.code, exc.message, exc.status) from exc
    return SentMessageOut.model_validate(sent)
