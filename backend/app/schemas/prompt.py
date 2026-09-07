from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.base import TimestampedOut


class PromptIn(BaseModel):
    text: str = Field(min_length=1)


class PromptOut(TimestampedOut):
    text: str
    is_active: bool
    missing_placeholders: list[str] = []
