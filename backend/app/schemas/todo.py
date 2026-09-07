from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.todo import TodoStatus, TodoType
from app.schemas.base import TimestampedOut


class TodoOut(TimestampedOut):
    type: TodoType
    title: str
    contact_id: int
    draft_id: int | None
    sent_message_id: int | None
    due_at: datetime
    status: TodoStatus
    completed_at: datetime | None


class TodoIn(BaseModel):
    type: TodoType = TodoType.MANUAL
    title: str = Field(min_length=1, max_length=200)
    contact_id: int
    due_at: datetime


class TodoPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_at: datetime | None = None
    status: TodoStatus | None = None


class TodoSendIn(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)


class SentMessageOut(TimestampedOut):
    contact_id: int
    subject: str
    body: str
    sent_at: datetime
    delivery_status: str
    error: str | None
