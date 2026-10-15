"""Unit test for the structlog redactor (T044 / SC-005).

Confirms that IMAP credential fields are dropped from log event dicts, matching the
SMTP credential handling. Both plaintext (`imap_username`, `imap_password`) and Fernet
ciphertext (`imap_username_ct`, `imap_password_ct`) columns are redacted at the
processor boundary.
"""
from __future__ import annotations

from app.logging import _redact


def _run(event_dict: dict) -> dict:
    # Second/third args to a structlog processor are the logger + method name; the
    # redactor ignores both.
    return _redact(None, "info", event_dict)


def test_imap_credentials_redacted() -> None:
    payload = {
        "event": "imap_connect",
        "imap_username": "operator@mailbox.org",
        "imap_password": "shhh-plaintext",
        "imap_username_ct": b"gAAAA-ciphertext",
        "imap_password_ct": b"gAAAA-more-ciphertext",
        # Sanity anchor — non-sensitive fields survive.
        "imap_host": "imap.mailbox.org",
        "imap_port": 993,
    }
    out = _run(payload)
    assert out["imap_username"] == "[REDACTED]"
    assert out["imap_password"] == "[REDACTED]"
    assert out["imap_username_ct"] == "[REDACTED]"
    assert out["imap_password_ct"] == "[REDACTED]"
    assert out["imap_host"] == "imap.mailbox.org"
    assert out["imap_port"] == 993


def test_smtp_credentials_also_redacted() -> None:
    """Same rule for SMTP — regression guard so IMAP + SMTP stay symmetric."""
    payload = {
        "event": "smtp_send",
        "smtp_username": "u",
        "smtp_password": "p",
        "smtp_username_ct": b"cipher",
        "smtp_password_ct": b"cipher",
    }
    out = _run(payload)
    assert out["smtp_username"] == "[REDACTED]"
    assert out["smtp_password"] == "[REDACTED]"
    assert out["smtp_username_ct"] == "[REDACTED]"
    assert out["smtp_password_ct"] == "[REDACTED]"


def test_nested_credentials_redacted() -> None:
    """Deep-scan works for nested dicts (e.g. context-vars merged in)."""
    payload = {"context": {"imap_password": "shhh", "user_visible": "ok"}}
    out = _run(payload)
    assert out["context"]["imap_password"] == "[REDACTED]"
    assert out["context"]["user_visible"] == "ok"
