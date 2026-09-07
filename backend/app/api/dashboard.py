from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.security.auth import require_auth
from app.services.dashboard import build_overview
from app.services.todo_promotion import promote_scheduled_todos

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth)],
)


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    # Match the contract: scheduled todos that are now due should count as "open" everywhere
    # the dashboard tallies, so promote before we start counting.
    promote_scheduled_todos(db)
    return build_overview(db)
