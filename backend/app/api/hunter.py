"""Pre-persistence Hunter Domain lookup endpoint (FR-004a).

Called from the Leads screen when the operator clicks "Look up domain" after entering a
company name — before any Organisation or Contact row exists. On success returns the
resolved domain; on Hunter "no result" returns HTTP 200 with `domain=null` and a hint
message (per FR-004b, the operator can type the domain by hand to unlock the gate).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import api_error
from app.db import get_db
from app.integrations import hunter
from app.models.settings import Settings as SettingsRow
from app.schemas.hunter import HunterDomainLookupIn, HunterDomainLookupOut
from app.security import secrets as secret_helpers
from app.security.auth import require_auth

router = APIRouter(
    prefix="/hunter",
    tags=["hunter"],
    dependencies=[Depends(require_auth)],
)


def _hunter_api_key(db: Session) -> str:
    settings = db.get(SettingsRow, 1)
    if settings is None or settings.hunter_api_key_ct is None:
        raise api_error(
            "credential_not_set",
            "Hunter API key is not configured. Set it in Settings.",
            400,
        )
    return secret_helpers.decrypt(settings.hunter_api_key_ct)


@router.post("/domain-lookup", response_model=HunterDomainLookupOut)
def domain_lookup(body: HunterDomainLookupIn, db: Session = Depends(get_db)) -> HunterDomainLookupOut:
    api_key = _hunter_api_key(db)
    try:
        domain = hunter.resolve_domain(body.company_name, api_key)
    except hunter.HunterCredentialError as exc:
        raise api_error("credential_not_set", str(exc), 400) from exc
    except hunter.HunterError as exc:
        raise api_error("hunter_error", str(exc), 502) from exc

    if domain is None:
        return HunterDomainLookupOut(
            domain=None,
            message=(
                f"No domain found for '{body.company_name}'. "
                "Enter the domain manually to continue."
            ),
        )
    return HunterDomainLookupOut(domain=domain)
