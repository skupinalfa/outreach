"""PATCH /api/v1/settings — secrets round-trip through Fernet; empty string clears."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers


def test_patch_encrypts_and_persists_secret(
    authed: TestClient, session_factory
) -> None:
    response = authed.patch(
        "/api/v1/settings",
        json={"hunter_api_key": "new-hunter-key"},
    )
    assert response.status_code == 200
    assert response.json()["hunter_api_key_set"] is True

    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        assert row.hunter_api_key_ct is not None
        assert secret_helpers.decrypt(row.hunter_api_key_ct) == "new-hunter-key"


def test_empty_string_clears_secret(authed: TestClient, session_factory) -> None:
    authed.patch("/api/v1/settings", json={"openai_api_key": "some-key"})

    response = authed.patch("/api/v1/settings", json={"openai_api_key": ""})
    assert response.status_code == 200
    assert response.json()["openai_api_key_set"] is False

    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        assert row.openai_api_key_ct is None


def test_omitted_field_is_not_touched(authed: TestClient, session_factory) -> None:
    authed.patch(
        "/api/v1/settings",
        json={"hunter_api_key": "keep-me", "openai_api_key": "openai-secret"},
    )
    authed.patch("/api/v1/settings", json={"openai_model": "gpt-5.6-luna"})

    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        assert row.hunter_api_key_ct is not None
        assert secret_helpers.decrypt(row.hunter_api_key_ct) == "keep-me"
        assert row.openai_api_key_ct is not None


def test_smtp_nested_patch(authed: TestClient, session_factory) -> None:
    response = authed.patch(
        "/api/v1/settings",
        json={
            "smtp": {
                "host": "smtp.mailbox.org",
                "port": 465,
                "username": "u",
                "password": "p",
            }
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["smtp"]["host"] == "smtp.mailbox.org"
    assert body["smtp"]["port"] == 465
    assert body["smtp"]["username_set"] is True
    assert body["smtp"]["password_set"] is True

    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        assert secret_helpers.decrypt(row.smtp_username_ct) == "u"
        assert secret_helpers.decrypt(row.smtp_password_ct) == "p"


def test_preferences_update(authed: TestClient) -> None:
    response = authed.patch(
        "/api/v1/settings",
        json={
            "sender_display_name": "Alfred",
            "sender_email": "alfred@example.com",
            "follow_up_cadence_days": 3,
            "openai_model": "gpt-5.6-pro",
            "timezone": "Europe/Zurich",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sender_display_name"] == "Alfred"
    assert body["sender_email"] == "alfred@example.com"
    assert body["follow_up_cadence_days"] == 3
    assert body["openai_model"] == "gpt-5.6-pro"
    assert body["timezone"] == "Europe/Zurich"


def test_cadence_out_of_range_rejected(authed: TestClient) -> None:
    response = authed.patch("/api/v1/settings", json={"follow_up_cadence_days": 90})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_blank_sender_email_does_not_drop_hunter_key(
    authed: TestClient, session_factory
) -> None:
    """Regression: the frontend used to send every field on save, including
    `sender_email: ""` for an unfilled input. Pydantic's `EmailStr` rejected `""` and
    422'd the whole PATCH, so a Hunter key set in the same request never persisted."""
    response = authed.patch(
        "/api/v1/settings",
        json={"hunter_api_key": "sk-hunter", "sender_email": ""},
    )
    assert response.status_code == 200
    assert response.json()["hunter_api_key_set"] is True

    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        assert row.hunter_api_key_ct is not None
        assert secret_helpers.decrypt(row.hunter_api_key_ct) == "sk-hunter"
