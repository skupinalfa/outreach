"""On-render helper — promotes any `scheduled` todo whose `due_at` is in the past to `open`.

Runs as a single UPDATE from `GET /todos` and `GET /dashboard/overview` handlers. No
background worker — the platform is single-operator and this is cheap.
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.todo import Todo, TodoStatus


def promote_scheduled_todos(db: Session) -> int:
    result = db.execute(
        update(Todo)
        .where(Todo.status == TodoStatus.SCHEDULED, Todo.due_at <= func.now())
        .values(status=TodoStatus.OPEN)
    )
    return result.rowcount or 0
