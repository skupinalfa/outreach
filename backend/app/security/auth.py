import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models.session import Session as SessionRow
from app.models.settings import Settings as SettingsRow

SESSION_COOKIE = "sid"


class AuthError(HTTPException):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": code, "message": message}},
        )


def hash_password(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plaintext: str, hashed: str) -> bool:
    return bcrypt.checkpw(plaintext.encode(), hashed.encode())


def _new_token() -> str:
    return secrets.token_urlsafe(48)


def _expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(hours=get_settings().session_ttl_hours)


def login(db: Session, password: str) -> SessionRow:
    row = db.get(SettingsRow, 1)
    if row is None or row.master_password_hash is None:
        raise AuthError("authentication_failed", "Master password is not set.")
    if not verify_password(password, row.master_password_hash):
        raise AuthError("authentication_failed", "Wrong password.")

    session = SessionRow(id=_new_token(), expires_at=_expires_at())
    db.add(session)
    db.flush()
    return session


def logout(db: Session, sid: str) -> None:
    session = db.get(SessionRow, sid)
    if session is not None:
        db.delete(session)


def touch(session: SessionRow) -> None:
    session.expires_at = _expires_at()


def require_auth(
    db: Session = Depends(get_db),
    sid: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> SessionRow:
    if not sid:
        raise AuthError("authentication_required", "No session cookie.")
    session = db.get(SessionRow, sid)
    if session is None or session.expires_at < datetime.now(UTC):
        raise AuthError("authentication_required", "Session expired.")
    touch(session)
    return session
