"""Pydantic schemas for the pre-persistence Hunter Domain lookup endpoint (FR-004a).

This endpoint is called from the Leads screen *before* the operator has committed a
contact or organisation, so the schemas are scoped to the integration and independent
of the Organisation/Contact schemas.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HunterDomainLookupIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)


class HunterDomainLookupOut(BaseModel):
    domain: str | None
    confidence: float | None = None
    source: Literal["hunter"] = "hunter"
    message: str | None = None
