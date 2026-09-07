from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.errors import not_found
from app.db import get_db
from app.models.prompt import Prompt
from app.schemas.prompt import PromptIn, PromptOut
from app.security.auth import require_auth
from app.services.placeholder_validator import missing_placeholders

router = APIRouter(
    prefix="/prompts",
    tags=["prompts"],
    dependencies=[Depends(require_auth)],
)


def _serialise(prompt: Prompt) -> PromptOut:
    view = PromptOut.model_validate(prompt)
    view.missing_placeholders = missing_placeholders(prompt.text)
    return view


@router.get("/active", response_model=PromptOut)
def get_active(db: Session = Depends(get_db)) -> PromptOut:
    active = db.execute(select(Prompt).where(Prompt.is_active.is_(True))).scalar_one_or_none()
    if active is None:
        raise not_found("Active prompt")
    return _serialise(active)


@router.get("/history", response_model=list[PromptOut])
def get_history(db: Session = Depends(get_db)) -> list[PromptOut]:
    rows = (
        db.execute(select(Prompt).order_by(desc(Prompt.created_at)).limit(20))
        .scalars()
        .all()
    )
    return [_serialise(p) for p in rows]


@router.put("/active", response_model=PromptOut)
def replace_active(body: PromptIn, db: Session = Depends(get_db)) -> PromptOut:
    """Prompts are append-only versions: the previous active row is flipped to inactive and a
    new row is inserted as active in the same transaction. Old drafts keep referring to their
    snapshot, so history remains interpretable (data-model.md §prompt)."""
    previous = db.execute(select(Prompt).where(Prompt.is_active.is_(True))).scalar_one_or_none()
    if previous is not None:
        previous.is_active = False
        # Flush the false state before inserting the new active row so the partial-unique index
        # on `is_active = true` sees only one active row at a time.
        db.flush()

    new_active = Prompt(text=body.text, is_active=True)
    db.add(new_active)
    db.flush()
    return _serialise(new_active)
