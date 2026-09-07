from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import api_error, conflict, not_found
from app.db import get_db
from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.schemas.base import PaginatedOut
from app.schemas.contact import ContactIn, ContactOut, ContactPatch, DraftSummary
from app.schemas.delete_impact import DeleteImpactOut
from app.security.auth import require_auth
from app.services.delete_impact import contact_impact
from app.services.enrichment import EnrichmentError, enrich_contact

router = APIRouter(
    prefix="/contacts",
    tags=["contacts"],
    dependencies=[Depends(require_auth)],
)


def _serialise(db: Session, contact: Contact) -> ContactOut:
    latest = db.execute(
        select(Draft)
        .where(Draft.contact_id == contact.id)
        .order_by(desc(Draft.generated_at))
        .limit(1)
    ).scalar_one_or_none()
    payload = ContactOut.model_validate(contact)
    if latest is not None:
        payload.latest_draft = DraftSummary(
            id=latest.id,
            subject=latest.subject,
            generated_at=latest.generated_at,
        )
    return payload


@router.get("", response_model=PaginatedOut[ContactOut])
def list_contacts(
    db: Session = Depends(get_db),
    organisation_id: int | None = None,
    status_: Annotated[ContactStatus | None, Query(alias="status")] = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PaginatedOut[ContactOut]:
    base = select(Contact)
    count_q = select(func.count()).select_from(Contact)
    if organisation_id is not None:
        base = base.where(Contact.organisation_id == organisation_id)
        count_q = count_q.where(Contact.organisation_id == organisation_id)
    if status_ is not None:
        base = base.where(Contact.status == status_)
        count_q = count_q.where(Contact.status == status_)
    if q:
        pattern = f"%{q.lower()}%"
        clause = or_(
            func.lower(Contact.first_name).like(pattern),
            func.lower(Contact.last_name).like(pattern),
            Contact.email.ilike(pattern),
        )
        base = base.where(clause)
        count_q = count_q.where(clause)

    total = db.execute(count_q).scalar_one()
    rows = (
        db.execute(
            base.order_by(Contact.last_name.asc(), Contact.first_name.asc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    items = [_serialise(db, c) for c in rows]
    return PaginatedOut(items=items, total=total)


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create(body: ContactIn, db: Session = Depends(get_db)) -> ContactOut:
    org = db.get(Organisation, body.organisation_id)
    if org is None:
        raise not_found("Organisation")
    contact = Contact(
        organisation_id=body.organisation_id,
        first_name=body.first_name,
        last_name=body.last_name,
        gender=body.gender,
        email=body.email,
        position=body.position,
        notes=body.notes,
    )
    db.add(contact)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("A contact with this email already exists in the organisation.") from exc
    return _serialise(db, contact)


@router.get("/{contact_id}", response_model=ContactOut)
def get_one(contact_id: int, db: Session = Depends(get_db)) -> ContactOut:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("Contact")
    return _serialise(db, contact)


@router.patch("/{contact_id}", response_model=ContactOut)
def patch(contact_id: int, body: ContactPatch, db: Session = Depends(get_db)) -> ContactOut:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("Contact")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("A contact with this email already exists in the organisation.") from exc
    return _serialise(db, contact)


@router.get("/{contact_id}/delete-impact", response_model=DeleteImpactOut)
def delete_impact(contact_id: int, db: Session = Depends(get_db)) -> DeleteImpactOut:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("Contact")
    return contact_impact(db, contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise not_found("Contact")
    db.delete(contact)


@router.post("/{contact_id}/enrich", response_model=ContactOut)
def enrich(contact_id: int, db: Session = Depends(get_db)) -> ContactOut:
    try:
        contact = enrich_contact(db, contact_id)
    except EnrichmentError as exc:
        # FR-029: audit fields (`last_enriched_at`, `last_enrichment_error`) must survive
        # the failure. The service has already mutated the ORM object; flush + commit
        # persists just that before we re-raise.
        db.commit()
        raise api_error(exc.code, exc.message, exc.status) from exc
    return _serialise(db, contact)
