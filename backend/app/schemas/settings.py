"""Settings API schemas.

The output shape hides ciphertext entirely — secret columns become `*_set` booleans so the
UI can render "•••••• (set)" placeholders. Patching accepts plaintext for secrets; an empty
string clears the value.
"""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, EmailStr, Field


def _blank_to_none(value: Any) -> Any:
    """Callers sometimes submit `""` for "no value" on optional fields; treat that as `None`.

    This keeps `EmailStr` validation strict while still tolerating the common frontend habit
    of sending every form field even when empty. Without this, a single blank optional field
    would 422 the whole PATCH and drop the useful fields alongside it.
    """
    if value == "":
        return None
    return value


BlankableEmail = Annotated[EmailStr | None, BeforeValidator(_blank_to_none)]


class SmtpView(BaseModel):
    host: str | None = None
    port: int | None = None
    username_set: bool = False
    password_set: bool = False


class ImapView(BaseModel):
    host: str | None = None
    port: int | None = None
    username_set: bool = False
    password_set: bool = False
    use_tls: bool = True
    drafts_folder: str | None = None  # operator override
    drafts_folder_detected: str | None = None  # auto-detected cache


class SettingsOut(BaseModel):
    hunter_api_key_set: bool = False
    openai_api_key_set: bool = False
    smtp: SmtpView = Field(default_factory=SmtpView)
    imap: ImapView = Field(default_factory=ImapView)
    sender_display_name: str | None = None
    sender_email: str | None = None
    follow_up_cadence_days: int = 5
    default_template_id: int | None = None
    openai_model: str = "gpt-5.6-luna"
    timezone: str = "Europe/Berlin"
    master_password_set: bool = False


class SmtpPatch(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None


class ImapPatch(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_tls: bool | None = None
    drafts_folder: str | None = None


class SettingsPatch(BaseModel):
    """All fields optional. For secrets and free-form strings, `""` clears the stored value."""

    hunter_api_key: str | None = None
    openai_api_key: str | None = None
    smtp: SmtpPatch | None = None
    imap: ImapPatch | None = None
    sender_display_name: str | None = None
    sender_email: BlankableEmail = None
    follow_up_cadence_days: int | None = Field(default=None, ge=1, le=30)
    default_template_id: int | None = None
    openai_model: str | None = None
    timezone: str | None = None


class TestConnectionOut(BaseModel):
    ok: bool
    message: str


class ImapTestConnectionOut(TestConnectionOut):
    resolved_drafts_folder: str | None = None


class HunterTestIn(BaseModel):
    api_key: str | None = None


class OpenAITestIn(BaseModel):
    api_key: str | None = None


class SmtpTestIn(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None


class ImapTestIn(BaseModel):
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    use_tls: bool | None = None
