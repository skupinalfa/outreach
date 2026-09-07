"""Settings service — reads/writes the singleton Settings row.

Semantics:
- `get_settings_view` decrypts nothing; secrets show up only as `*_set` booleans.
- `patch_settings`: any field that arrives in the payload is applied. For secret-bearing
  fields, an empty string clears the ciphertext; a non-empty string is Fernet-encrypted;
  `None` means "not provided" and is skipped.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.settings import Settings as SettingsRow
from app.schemas.settings import SettingsOut, SettingsPatch, SmtpView
from app.security import secrets as secret_helpers


def _row(db: Session) -> SettingsRow:
    row = db.get(SettingsRow, 1)
    if row is None:
        row = SettingsRow(id=1)
        db.add(row)
        db.flush()
    return row


def get_settings_view(db: Session) -> SettingsOut:
    row = _row(db)
    return SettingsOut(
        hunter_api_key_set=row.hunter_api_key_ct is not None,
        openai_api_key_set=row.openai_api_key_ct is not None,
        smtp=SmtpView(
            host=row.smtp_host,
            port=row.smtp_port,
            username_set=row.smtp_username_ct is not None,
            password_set=row.smtp_password_ct is not None,
        ),
        sender_display_name=row.sender_display_name,
        sender_email=row.sender_email,
        follow_up_cadence_days=row.follow_up_cadence_days,
        default_template_id=row.default_template_id,
        openai_model=row.openai_model,
        timezone=row.timezone,
        master_password_set=row.master_password_hash is not None,
    )


def _apply_secret(current: bytes | None, incoming: str | None) -> bytes | None:
    """None → keep. Empty string → clear. Non-empty → encrypt."""
    if incoming is None:
        return current
    if incoming == "":
        return None
    return secret_helpers.encrypt(incoming)


def _apply_optional_str(current: str | None, incoming: str | None) -> str | None:
    if incoming is None:
        return current
    if incoming == "":
        return None
    return incoming


def patch_settings(db: Session, patch: SettingsPatch) -> SettingsOut:
    row = _row(db)
    data = patch.model_dump(exclude_unset=True)

    if "hunter_api_key" in data:
        row.hunter_api_key_ct = _apply_secret(row.hunter_api_key_ct, data["hunter_api_key"])
    if "openai_api_key" in data:
        row.openai_api_key_ct = _apply_secret(row.openai_api_key_ct, data["openai_api_key"])

    if "smtp" in data and data["smtp"] is not None:
        smtp = data["smtp"]
        if "host" in smtp:
            row.smtp_host = _apply_optional_str(row.smtp_host, smtp["host"])
        if "port" in smtp:
            row.smtp_port = smtp["port"]
        if "username" in smtp:
            row.smtp_username_ct = _apply_secret(row.smtp_username_ct, smtp["username"])
        if "password" in smtp:
            row.smtp_password_ct = _apply_secret(row.smtp_password_ct, smtp["password"])

    if "sender_display_name" in data:
        row.sender_display_name = _apply_optional_str(
            row.sender_display_name, data["sender_display_name"]
        )
    if "sender_email" in data:
        row.sender_email = _apply_optional_str(row.sender_email, data["sender_email"])
    if "follow_up_cadence_days" in data and data["follow_up_cadence_days"] is not None:
        row.follow_up_cadence_days = data["follow_up_cadence_days"]
    if "default_template_id" in data:
        row.default_template_id = data["default_template_id"]
    if "openai_model" in data and data["openai_model"]:
        row.openai_model = data["openai_model"]
    if "timezone" in data and data["timezone"]:
        row.timezone = data["timezone"]

    db.flush()
    return get_settings_view(db)
