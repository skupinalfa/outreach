"""POST /api/v1/settings/test/{hunter,openai,smtp}.

Hunter and OpenAI are exercised by monkey-patching the boundaries. SMTP is exercised against
an in-process `aiosmtpd` — this is the same server used in `test_todos_send_api.py`.
"""
from __future__ import annotations

import socket

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
from fastapi.testclient import TestClient

from app.integrations import hunter, openai_client
from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers


def _seed(session_factory, **columns) -> None:
    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        for key, value in columns.items():
            setattr(row, key, value)
        session.commit()


def test_hunter_uses_proposed_body_key(
    authed: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_resolve(company: str, api_key: str) -> str:
        captured["api_key"] = api_key
        return "stripe.com"

    monkeypatch.setattr(hunter, "resolve_domain", fake_resolve)

    response = authed.post("/api/v1/settings/test/hunter", json={"api_key": "unsaved-key"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert captured["api_key"] == "unsaved-key"


def test_hunter_falls_back_to_persisted(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(session_factory, hunter_api_key_ct=secret_helpers.encrypt("persisted-hunter"))
    captured: dict[str, str] = {}

    def fake_resolve(company: str, api_key: str) -> str:
        captured["api_key"] = api_key
        return "stripe.com"

    monkeypatch.setattr(hunter, "resolve_domain", fake_resolve)

    response = authed.post("/api/v1/settings/test/hunter", json={})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["api_key"] == "persisted-hunter"


def test_hunter_no_key_returns_400(authed: TestClient) -> None:
    response = authed.post("/api/v1/settings/test/hunter", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"


def test_hunter_bad_key_reports_ok_false(
    authed: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise hunter.HunterCredentialError("Hunter rejected the API key.")

    monkeypatch.setattr(hunter, "resolve_domain", _boom)

    response = authed.post("/api/v1/settings/test/hunter", json={"api_key": "bad"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "rejected" in body["message"].lower()


def test_openai_uses_proposed_body_key(
    authed: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def fake_probe(api_key: str) -> None:
        captured["api_key"] = api_key

    monkeypatch.setattr(openai_client, "test_credentials", fake_probe)

    response = authed.post("/api/v1/settings/test/openai", json={"api_key": "sk-proposed"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["api_key"] == "sk-proposed"


def test_openai_bad_key_reports_ok_false(
    authed: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(_api_key: str) -> None:
        raise openai_client.OpenAICredentialError("OpenAI rejected the API key.")

    monkeypatch.setattr(openai_client, "test_credentials", _boom)

    response = authed.post("/api/v1/settings/test/openai", json={"api_key": "bad"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "rejected" in body["message"].lower()


def _authenticator(server, session, envelope, mechanism, auth_data):
    if (
        isinstance(auth_data, LoginPassword)
        and auth_data.login == b"user"
        and auth_data.password == b"secret"
    ):
        return AuthResult(success=True)
    return AuthResult(success=False, handled=False)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def smtp_server():
    class Handler:
        async def handle_DATA(self, server, session, envelope):  # noqa: N802
            return "250 OK"

    port = _free_port()
    controller = Controller(
        Handler(),
        hostname="127.0.0.1",
        port=port,
        authenticator=_authenticator,
        auth_required=True,
        auth_require_tls=False,
    )
    controller.start()
    try:
        yield port
    finally:
        controller.stop()


def test_smtp_happy_path(authed: TestClient, smtp_server) -> None:
    response = authed.post(
        "/api/v1/settings/test/smtp",
        json={
            "host": "127.0.0.1",
            "port": smtp_server,
            "username": "user",
            "password": "secret",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True


def test_smtp_wrong_password_reports_ok_false(authed: TestClient, smtp_server) -> None:
    response = authed.post(
        "/api/v1/settings/test/smtp",
        json={
            "host": "127.0.0.1",
            "port": smtp_server,
            "username": "user",
            "password": "wrong",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False


def test_smtp_missing_fields_returns_400(authed: TestClient) -> None:
    response = authed.post(
        "/api/v1/settings/test/smtp",
        json={"host": "127.0.0.1", "port": 1025},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"
