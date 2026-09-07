from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.base import TimestampedOut


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject_hint: str | None = None
    body: str = Field(min_length=1)


class TemplatePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    subject_hint: str | None = None
    body: str | None = Field(default=None, min_length=1)
    is_archived: bool | None = None


class TemplateOut(TimestampedOut):
    name: str
    subject_hint: str | None
    body: str
    is_archived: bool
    missing_placeholders: list[str] = []
