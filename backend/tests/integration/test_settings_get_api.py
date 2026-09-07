"""GET /api/v1/settings — returns only is-set flags for secrets, no ciphertext."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers


def test_bootstrapped_shape_has_no_secrets(authed: TestClient) -> None:
    response = authed.get("/api/v1/settings")
    assert response.status_code == 200
    body = response.json()

    for key in body:
        assert not key.endswith("_ct"), f"Ciphertext field leaked: {key}"

    assert body["hunter_api_key_set"] is False
    assert body["openai_api_key_set"] is False
    assert body["smtp"] == {"host": None, "port": None, "username_set": False, "password_set": False}
    assert body["master_password_set"] is True  # seeded by the authed fixture
    assert body["timezone"] == "Europe/Berlin"
    assert body["openai_model"] == "gpt-5.6-luna"


def test_secrets_appear_only_as_boolean_flags(
    authed: TestClient, session_factory
) -> None:
    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        row.hunter_api_key_ct = secret_helpers.encrypt("hunter-plaintext-abc")
        row.openai_api_key_ct = secret_helpers.encrypt("openai-plaintext-xyz")
        row.smtp_host = "smtp.example.com"
        row.smtp_port = 465
        row.smtp_username_ct = secret_helpers.encrypt("mailbox-login-qqq")
        row.smtp_password_ct = secret_helpers.encrypt("mailbox-pw-zzz")
        session.commit()

    body = authed.get("/api/v1/settings").json()
    assert body["hunter_api_key_set"] is True
    assert body["openai_api_key_set"] is True
    assert body["smtp"]["host"] == "smtp.example.com"
    assert body["smtp"]["port"] == 465
    assert body["smtp"]["username_set"] is True
    assert body["smtp"]["password_set"] is True

    serialised = str(body)
    for plaintext in (
        "hunter-plaintext-abc",
        "openai-plaintext-xyz",
        "mailbox-login-qqq",
        "mailbox-pw-zzz",
    ):
        assert plaintext not in serialised, f"Plaintext leaked in response: {plaintext}"
