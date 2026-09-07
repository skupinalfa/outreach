from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.base import TimestampedOut


class DraftIn(BaseModel):
    template_id: int


class DraftPatch(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None, min_length=1)


class DraftOut(TimestampedOut):
    contact_id: int
    template_id: int
    prompt_id: int
    subject: str
    body: str
    generated_at: datetime
