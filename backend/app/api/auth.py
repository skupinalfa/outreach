from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as SASession

from app.config import get_settings
from app.db import get_db
from app.models.settings import Settings as SettingsRow
from app.security import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class PasswordIn(BaseModel):
    password: str = Field(min_length=8)


class AuthMeOut(BaseModel):
    authenticated: bool
    master_password_set: bool


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(body: PasswordIn, response: Response, db: SASession = Depends(get_db)) -> None:
    session = auth_service.login(db, body.password)
    response.set_cookie(
        key=auth_service.SESSION_COOKIE,
        value=session.id,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        expires=session.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session=Depends(auth_service.require_auth),
    db: SASession = Depends(get_db),
) -> None:
    auth_service.logout(db, session.id)
    response.delete_cookie(auth_service.SESSION_COOKIE)


@router.get("/me", response_model=AuthMeOut)
def me(
    db: SASession = Depends(get_db),
    sid: str | None = Cookie(default=None, alias=auth_service.SESSION_COOKIE),
) -> AuthMeOut:
    row = db.get(SettingsRow, 1)
    master_set = bool(row and row.master_password_hash)
    try:
        auth_service.require_auth(db=db, sid=sid)
        return AuthMeOut(authenticated=True, master_password_set=master_set)
    except HTTPException:
        return AuthMeOut(authenticated=False, master_password_set=master_set)


@router.post("/bootstrap", status_code=status.HTTP_204_NO_CONTENT)
def bootstrap(body: PasswordIn, db: SASession = Depends(get_db)) -> None:
    row = db.get(SettingsRow, 1)
    if row is None:
        row = SettingsRow(id=1)
        db.add(row)
        db.flush()
    if row.master_password_hash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "bootstrap_already_done",
                    "message": "Master password already configured.",
                }
            },
        )
    row.master_password_hash = auth_service.hash_password(body.password)
