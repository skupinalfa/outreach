from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class DeleteImpactTarget(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: Literal["organisation", "contact"]
    id: int
    name: str


class DeleteImpactCounts(BaseModel):
    contacts: int
    drafts: int
    sent_messages: int
    open_todos: int


class DeleteImpactOut(BaseModel):
    target: DeleteImpactTarget
    counts: DeleteImpactCounts
