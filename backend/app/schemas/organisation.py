from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.base import TimestampedOut


class OrganisationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=255)
    notes: str = ""


class OrganisationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class OrganisationOut(TimestampedOut):
    name: str
    domain: str | None
    notes: str
