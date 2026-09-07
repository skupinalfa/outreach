from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import conflict, not_found
from app.db import get_db
from app.models.draft import Draft
from app.models.template import Template
from app.schemas.template import TemplateIn, TemplateOut, TemplatePatch
from app.security.auth import require_auth
from app.services.placeholder_validator import missing_placeholders

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(require_auth)],
)


def _serialise(t: Template) -> TemplateOut:
    view = TemplateOut.model_validate(t)
    view.missing_placeholders = missing_placeholders(t.body)
    return view


@router.get("", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    include_archived: bool = Query(default=False),
) -> list[TemplateOut]:
    stmt = select(Template)
    if not include_archived:
        stmt = stmt.where(Template.is_archived.is_(False))
    rows = db.execute(stmt.order_by(Template.name.asc())).scalars().all()
    return [_serialise(t) for t in rows]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create(body: TemplateIn, db: Session = Depends(get_db)) -> TemplateOut:
    template = Template(name=body.name, subject_hint=body.subject_hint, body=body.body)
    db.add(template)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("A template with this name already exists.") from exc
    return _serialise(template)


@router.get("/{template_id}", response_model=TemplateOut)
def get_one(template_id: int, db: Session = Depends(get_db)) -> TemplateOut:
    template = db.get(Template, template_id)
    if template is None:
        raise not_found("Template")
    return _serialise(template)


@router.patch("/{template_id}", response_model=TemplateOut)
def patch(template_id: int, body: TemplatePatch, db: Session = Depends(get_db)) -> TemplateOut:
    template = db.get(Template, template_id)
    if template is None:
        raise not_found("Template")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("A template with this name already exists.") from exc
    return _serialise(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(template_id: int, db: Session = Depends(get_db)):
    """Hard-delete if no draft references the template. Otherwise archive it so the
    referencing drafts keep their snapshots interpretable (data-model.md, US4 acceptance)."""
    template = db.get(Template, template_id)
    if template is None:
        raise not_found("Template")

    referenced = db.execute(
        select(func.count()).select_from(Draft).where(Draft.template_id == template_id)
    ).scalar_one()

    if referenced:
        template.is_archived = True
    else:
        db.delete(template)
