from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import api_error
from app.db import get_db
from app.integrations import hunter, openai_client
from app.integrations import smtp as smtp_integration
from app.models.settings import Settings as SettingsRow
from app.schemas.settings import (
    HunterTestIn,
    OpenAITestIn,
    SettingsOut,
    SettingsPatch,
    SmtpTestIn,
    TestConnectionOut,
)
from app.security import secrets as secret_helpers
from app.security.auth import require_auth
from app.services import settings_service

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=SettingsOut)
def get_view(db: Session = Depends(get_db)) -> SettingsOut:
    return settings_service.get_settings_view(db)


@router.patch("", response_model=SettingsOut)
def patch(body: SettingsPatch, db: Session = Depends(get_db)) -> SettingsOut:
    return settings_service.patch_settings(db, body)


def _persisted_secret(db: Session, column: str) -> str | None:
    row = db.get(SettingsRow, 1)
    ct = getattr(row, column, None) if row else None
    if ct is None:
        return None
    return secret_helpers.decrypt(ct)


@router.post("/test/hunter", response_model=TestConnectionOut)
def test_hunter(body: HunterTestIn, db: Session = Depends(get_db)) -> TestConnectionOut:
    api_key = body.api_key if body.api_key else _persisted_secret(db, "hunter_api_key_ct")
    if not api_key:
        raise api_error("credential_not_set", "No Hunter API key to test.", 400)
    try:
        hunter.resolve_domain("Stripe", api_key)
        return TestConnectionOut(ok=True, message="Hunter accepted the API key.")
    except hunter.HunterCredentialError as exc:
        return TestConnectionOut(ok=False, message=str(exc))
    except hunter.HunterError as exc:
        return TestConnectionOut(ok=False, message=str(exc))


@router.post("/test/openai", response_model=TestConnectionOut)
def test_openai(body: OpenAITestIn, db: Session = Depends(get_db)) -> TestConnectionOut:
    api_key = body.api_key if body.api_key else _persisted_secret(db, "openai_api_key_ct")
    if not api_key:
        raise api_error("credential_not_set", "No OpenAI API key to test.", 400)
    try:
        openai_client.test_credentials(api_key)
        return TestConnectionOut(ok=True, message="OpenAI accepted the API key.")
    except openai_client.OpenAICredentialError as exc:
        return TestConnectionOut(ok=False, message=str(exc))
    except openai_client.OpenAIError as exc:
        return TestConnectionOut(ok=False, message=str(exc))


@router.post("/test/smtp", response_model=TestConnectionOut)
def test_smtp(body: SmtpTestIn, db: Session = Depends(get_db)) -> TestConnectionOut:
    row = db.get(SettingsRow, 1)
    host = body.host or (row.smtp_host if row else None)
    port = body.port or (row.smtp_port if row else None)
    username = body.username or _persisted_secret(db, "smtp_username_ct")
    password = body.password or _persisted_secret(db, "smtp_password_ct")
    if not host or not port or not username or not password:
        raise api_error("credential_not_set", "SMTP host/port/username/password required.", 400)
    try:
        smtp_integration.test_credentials(host, port, username, password)
        return TestConnectionOut(ok=True, message="SMTP accepted the credentials.")
    except smtp_integration.SmtpCredentialError as exc:
        return TestConnectionOut(ok=False, message=str(exc))
    except smtp_integration.SmtpError as exc:
        return TestConnectionOut(ok=False, message=str(exc))
