"""First-run seeding: fills the singleton Settings row, an initial Prompt, and a default Template
if the database is empty. Idempotent."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging import get_logger
from app.models.prompt import Prompt
from app.models.settings import Settings as SettingsRow
from app.models.template import Template
from app.security import auth as auth_service
from app.security import secrets as secret_helpers

_PROMPT_FALLBACK = (
    "Recherchiere zunächst das Unternehmen unter {domain} im Web.\n\n"
    "Schreibe anschließend eine personalisierte E-Mail an {last_name} "
    "(Anrede passend zu: {gender}).\n"
    "Orientiere dich stark an der Struktur und dem Tonfall dieser Vorlage:\n\n"
    "--- VORLAGE ---\n{template}\n--- ENDE VORLAGE ---\n\n"
    'Gib das Ergebnis als JSON zurück: {"subject": "...", "text": "..."}.'
)


def _read_prompt_seed() -> str:
    root = Path(__file__).resolve().parents[2]
    candidate = root / "prompt.txt"
    if candidate.exists() and candidate.stat().st_size > 20:
        return candidate.read_text(encoding="utf-8")
    return _PROMPT_FALLBACK


def bootstrap_settings(db: Session) -> None:
    log = get_logger("bootstrap")
    env = get_settings()

    row = db.get(SettingsRow, 1)
    if row is None:
        row = SettingsRow(id=1)
        db.add(row)
        db.flush()
        log.info("seeded_settings_row")

    if row.master_password_hash is None and env.initial_master_password is not None:
        row.master_password_hash = auth_service.hash_password(
            env.initial_master_password.get_secret_value()
        )
        log.info("seeded_master_password")

    if row.hunter_api_key_ct is None and env.hunter_api_key is not None:
        row.hunter_api_key_ct = secret_helpers.encrypt(env.hunter_api_key.get_secret_value())
    if row.openai_api_key_ct is None and env.openai_api_key is not None:
        row.openai_api_key_ct = secret_helpers.encrypt(env.openai_api_key.get_secret_value())
    if row.smtp_host is None and env.smtp_host:
        row.smtp_host = env.smtp_host
    if row.smtp_port is None and env.smtp_port:
        row.smtp_port = env.smtp_port
    if row.smtp_username_ct is None and env.smtp_username:
        row.smtp_username_ct = secret_helpers.encrypt(env.smtp_username)
    if row.smtp_password_ct is None and env.smtp_password is not None:
        row.smtp_password_ct = secret_helpers.encrypt(env.smtp_password.get_secret_value())
    if row.sender_display_name is None and env.sender_display_name:
        row.sender_display_name = env.sender_display_name
    if row.sender_email is None and env.sender_email:
        row.sender_email = env.sender_email


def bootstrap_prompt_and_template(db: Session) -> None:
    log = get_logger("bootstrap")

    seed_text = _read_prompt_seed()

    active = db.execute(select(Prompt).where(Prompt.is_active.is_(True))).scalar_one_or_none()
    if active is None:
        db.add(Prompt(text=seed_text, is_active=True))
        log.info("seeded_initial_prompt")

    any_template = db.execute(select(Template).limit(1)).scalar_one_or_none()
    if any_template is None:
        db.add(
            Template(
                name="Default",
                subject_hint=None,
                body=seed_text,
                is_archived=False,
            )
        )
        log.info("seeded_default_template")


def bootstrap_all(db: Session) -> None:
    bootstrap_settings(db)
    bootstrap_prompt_and_template(db)
