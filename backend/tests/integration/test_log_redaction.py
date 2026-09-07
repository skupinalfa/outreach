"""SC-005 log-redaction — no `password`, `api_key`, or `_ct` value must appear in structlog
output during a full enrich + generate + send flow.
"""
from __future__ import annotations

import socket

import pytest
import structlog
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations import hunter, openai_client
from app.models.contact import Contact, ContactStatus
from app.models.settings import Settings as SettingsRow
from app.models.template import Template
from app.models.todo import Todo, TodoType
from app.security import secrets as secret_helpers

_HUNTER_KEY = "hunter-super-secret-plaintext"
_OPENAI_KEY = "sk-openai-super-secret-plaintext"
_SMTP_USER = "smtp-user-plaintext"
_SMTP_PASS = "smtp-password-plaintext"


def _authenticator(server, session, envelope, mechanism, auth_data):
    if (
        isinstance(auth_data, LoginPassword)
        and auth_data.login == _SMTP_USER.encode()
        and auth_data.password == _SMTP_PASS.encode()
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


def test_no_secret_leaks_during_full_send_flow(
    authed: TestClient,
    session_factory,
    smtp_server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed all credentials the flow will exercise.
    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        row.hunter_api_key_ct = secret_helpers.encrypt(_HUNTER_KEY)
        row.openai_api_key_ct = secret_helpers.encrypt(_OPENAI_KEY)
        row.smtp_host = "127.0.0.1"
        row.smtp_port = smtp_server
        row.smtp_username_ct = secret_helpers.encrypt(_SMTP_USER)
        row.smtp_password_ct = secret_helpers.encrypt(_SMTP_PASS)
        row.sender_email = "sender@example.com"
        row.sender_display_name = "Alfred"
        template_id = session.execute(select(Template).limit(1)).scalar_one().id
        session.commit()

    # Stub the external boundaries so we don't hit real services.
    monkeypatch.setattr(hunter, "resolve_domain", lambda company, api_key: "stripe.com")
    monkeypatch.setattr(
        hunter,
        "find_email",
        lambda first, last, domain, api_key: hunter.EmailFinderResult(
            email="patrick@stripe.com",
            domain=domain,
            score=99,
            position="CEO",
            verification_status="valid",
        ),
    )
    monkeypatch.setattr(
        openai_client,
        "generate",
        lambda prompt, api_key, model="", max_tokens=0: '{"subject":"Hi","text":"Hello"}',
    )

    # Drive the full flow while capturing structlog output.
    with structlog.testing.capture_logs() as captured:
        org = authed.post(
            "/api/v1/organisations", json={"name": "Stripe", "domain": None}
        ).json()
        contact = authed.post(
            "/api/v1/contacts",
            json={
                "organisation_id": org["id"],
                "first_name": "Patrick",
                "last_name": "Collison",
                "gender": "m",
            },
        ).json()
        authed.post(f"/api/v1/contacts/{contact['id']}/enrich")
        # Bump status so the send transition works.
        with session_factory() as session:
            row = session.get(Contact, contact["id"])
            row.status = ContactStatus.ENRICHED
            session.commit()
        authed.post(
            f"/api/v1/contacts/{contact['id']}/drafts", json={"template_id": template_id}
        )
        with session_factory() as session:
            todo = session.execute(
                select(Todo).where(Todo.contact_id == contact["id"], Todo.type == TodoType.SEND)
            ).scalar_one()
            todo_id = todo.id
        authed.post(
            f"/api/v1/todos/{todo_id}/send",
            json={"subject": "s", "body": "b"},
        )

    serialised = repr(captured)
    for secret in (_HUNTER_KEY, _OPENAI_KEY, _SMTP_USER, _SMTP_PASS):
        assert secret not in serialised, f"Plaintext secret leaked in logs: {secret}"

    # Also confirm no Fernet ciphertext leaked.
    assert "gAAAA" not in serialised, "Fernet ciphertext leaked into structlog output."
