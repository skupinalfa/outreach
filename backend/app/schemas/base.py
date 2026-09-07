from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TimestampedOut(ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime


class PaginatedOut(BaseModel, Generic[T]):
    items: list[T]
    total: int


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | None = None


class ErrorOut(BaseModel):
    error: ErrorBody = Field(...)
