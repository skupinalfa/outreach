from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models.contact import ContactStatus
from app.schemas.base import TimestampedOut

Gender = Literal["m", "f", "d"]


class ContactIn(BaseModel):
    organisation_id: int
    first_name: str = Field(min_length=1, max_length=200)
    last_name: str = Field(min_length=1, max_length=200)
    gender: Gender | None = None
    email: EmailStr | None = None
    position: str | None = Field(default=None, max_length=200)
    notes: str = ""


class ContactPatch(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=200)
    last_name: str | None = Field(default=None, min_length=1, max_length=200)
    gender: Gender | None = None
    email: EmailStr | None = None
    position: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    status: ContactStatus | None = None


class DraftSummary(BaseModel):
    id: int
    subject: str
    generated_at: datetime


class ContactOut(TimestampedOut):
    organisation_id: int
    first_name: str
    last_name: str
    gender: Gender | None
    email: str | None
    position: str | None
    status: ContactStatus
    notes: str
    last_enriched_at: datetime | None
    last_enrichment_error: str | None
    last_generated_at: datetime | None
    last_generation_error: str | None
    latest_draft: DraftSummary | None = None
