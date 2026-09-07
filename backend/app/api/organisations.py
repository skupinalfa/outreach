from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import conflict, not_found
from app.db import get_db
from app.models.contact import Contact
from app.models.organisation import Organisation
from app.schemas.base import PaginatedOut
from app.schemas.contact import ContactOut
from app.schemas.delete_impact import DeleteImpactOut
from app.schemas.organisation import OrganisationIn, OrganisationOut, OrganisationPatch
from app.security.auth import require_auth
from app.services.delete_impact import organisation_impact

router = APIRouter(
    prefix="/organisations",
    tags=["organisations"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=PaginatedOut[OrganisationOut])
def list_organisations(
    db: Session = Depends(get_db),
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedOut[OrganisationOut]:
    base = select(Organisation)
    count_q = select(func.count()).select_from(Organisation)
    if q:
        pattern = f"%{q.lower()}%"
        # Case-insensitive substring match across name and domain.
        base = base.where(
            or_(func.lower(Organisation.name).like(pattern), Organisation.domain.ilike(pattern))
        )
        count_q = count_q.where(
            or_(func.lower(Organisation.name).like(pattern), Organisation.domain.ilike(pattern))
        )

    total = db.execute(count_q).scalar_one()
    rows = (
        db.execute(base.order_by(Organisation.name.asc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return PaginatedOut(items=[OrganisationOut.model_validate(o) for o in rows], total=total)


@router.post("", response_model=OrganisationOut, status_code=status.HTTP_201_CREATED)
def create(body: OrganisationIn, db: Session = Depends(get_db)) -> Organisation:
    org = Organisation(name=body.name, domain=body.domain, notes=body.notes)
    db.add(org)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("An organisation with this name already exists.") from exc
    return org


@router.get("/{org_id}", response_model=OrganisationOut)
def get_one(org_id: int, db: Session = Depends(get_db)) -> Organisation:
    org = db.get(Organisation, org_id)
    if org is None:
        raise not_found("Organisation")
    return org


@router.get("/{org_id}/contacts", response_model=list[ContactOut])
def list_contacts_of(org_id: int, db: Session = Depends(get_db)) -> list[ContactOut]:
    org = db.get(Organisation, org_id)
    if org is None:
        raise not_found("Organisation")
    contacts = (
        db.execute(
            select(Contact)
            .where(Contact.organisation_id == org_id)
            .order_by(Contact.last_name.asc(), Contact.first_name.asc())
        )
        .scalars()
        .all()
    )
    return [ContactOut.model_validate(c) for c in contacts]


@router.patch("/{org_id}", response_model=OrganisationOut)
def patch(org_id: int, body: OrganisationPatch, db: Session = Depends(get_db)) -> Organisation:
    org = db.get(Organisation, org_id)
    if org is None:
        raise not_found("Organisation")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("An organisation with this name already exists.") from exc
    return org


@router.get("/{org_id}/delete-impact", response_model=DeleteImpactOut)
def delete_impact(org_id: int, db: Session = Depends(get_db)) -> DeleteImpactOut:
    org = db.get(Organisation, org_id)
    if org is None:
        raise not_found("Organisation")
    return organisation_impact(db, org)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(org_id: int, db: Session = Depends(get_db)):
    # Cascades through the ON DELETE CASCADE FK on contact.organisation_id (see
    # migration 0002_org_cascade) which in turn cascades to draft, sent_message, and
    # todo. Frontend enforces the impact-count confirmation (see FR-027a).
    org = db.get(Organisation, org_id)
    if org is None:
        raise not_found("Organisation")
    db.delete(org)
