"""POST /todos/{id}/send — full path: SMTP delivery via aiosmtpd, todo done, sent record."""
from __future__ import annotations

import socket
from email.message import EmailMessage

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations import openai_client
from app.models.contact import Contact, ContactStatus
from app.models.organisation import Organisation
from app.models.sent_message import SentMessage
from app.models.settings import Settings as SettingsRow
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType
from app.security import secrets as secret_helpers


class _RecordingHandler:
    def __init__(self):
        self.messages: list[EmailMessage] = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        self.messages.append(envelope.content)
        return "250 OK"


def _authenticator(server, session, envelope, mechanism, auth_data):
    if isinstance(auth_data, LoginPassword) and auth_data.login == b"user" and auth_data.password == b"secret":
        return AuthResult(success=True)
    return AuthResult(success=False, handled=False)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def smtp_server():
    handler = _RecordingHandler()
    port = _free_port()
    controller = Controller(
        handler,
        hostname="127.0.0.1",
        port=port,
        authenticator=_authenticator,
        auth_required=True,
        auth_require_tls=False,
    )
    controller.start()
    try:
        yield controller, handler, port
    finally:
        controller.stop()


def _prepare_send_todo(
    authed: TestClient,
    session_factory,
    smtp_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, int]:
    with session_factory() as session:
        settings = session.get(SettingsRow, 1)
        settings.smtp_host = "127.0.0.1"
        settings.smtp_port = smtp_port
        settings.smtp_username_ct = secret_helpers.encrypt("user")
        settings.smtp_password_ct = secret_helpers.encrypt("secret")
        settings.sender_email = "sender@example.com"
        settings.sender_display_name = "Alfred"
        settings.openai_api_key_ct = secret_helpers.encrypt("test-openai-key")
        template_id = session.execute(select(Template).limit(1)).scalar_one().id
        session.commit()

    org = authed.post("/api/v1/organisations", json={"name": "Stripe", "domain": "stripe.com"}).json()
    contact = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org["id"],
            "first_name": "Patrick",
            "last_name": "Collison",
            "email": "patrick@stripe.com",
            "gender": "m",
        },
    ).json()

    # Skip enrichment for this test but simulate its status effect so the send flow
    # can transition ENRICHED -> CONTACTED per the state machine.
    with session_factory() as session:
        contact_row = session.get(Contact, contact["id"])
        contact_row.status = ContactStatus.ENRICHED
        session.commit()

    monkeypatch.setattr(
        openai_client,
        "generate",
        lambda prompt, api_key, model="", max_tokens=0: '{"subject":"Hallo","text":"Guten Tag"}',
    )
    authed.post(f"/api/v1/contacts/{contact['id']}/drafts", json={"template_id": template_id})

    with session_factory() as session:
        todo = session.execute(
            select(Todo).where(Todo.contact_id == contact["id"], Todo.type == TodoType.SEND)
        ).scalar_one()
        return todo.id, contact["id"]


def test_send_todo_delivers_and_marks_done(
    authed: TestClient,
    session_factory,
    smtp_server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _controller, handler, port = smtp_server
    todo_id, contact_id = _prepare_send_todo(authed, session_factory, port, monkeypatch)

    response = authed.post(
        f"/api/v1/todos/{todo_id}/send",
        json={"subject": "Edited subject", "body": "Edited body"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["subject"] == "Edited subject"

    assert len(handler.messages) == 1
    delivered = handler.messages[0].decode(errors="ignore")
    assert "Subject: Edited subject" in delivered
    assert "Edited body" in delivered

    with session_factory() as session:
        todo = session.get(Todo, todo_id)
        assert todo.status == TodoStatus.DONE
        assert todo.completed_at is not None
        assert todo.sent_message_id is not None

        contact = session.get(Contact, contact_id)
        assert contact.status == ContactStatus.CONTACTED

        sent = session.get(SentMessage, todo.sent_message_id)
        assert sent.subject == "Edited subject"
        assert sent.body == "Edited body"


def test_send_todo_missing_smtp_credentials_returns_400(
    authed: TestClient, session_factory
) -> None:
    with session_factory() as session:
        org = Organisation(name="Acme")
        session.add(org)
        session.flush()
        contact = Contact(
            organisation_id=org.id,
            first_name="A",
            last_name="B",
            email="a@acme.com",
        )
        session.add(contact)
        session.flush()
        todo = Todo(
            type=TodoType.SEND,
            title="send",
            contact_id=contact.id,
            due_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            status=TodoStatus.OPEN,
        )
        session.add(todo)
        session.commit()
        todo_id = todo.id

    response = authed.post(
        f"/api/v1/todos/{todo_id}/send",
        json={"subject": "s", "body": "b"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"
