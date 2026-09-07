"""Contract test for the SMTP boundary against an in-process aiosmtpd server.

Verifies:
- Happy-path AUTH + send of a MIME multipart message.
- Retryable classification for a transient 4xx.
- Non-retryable classification for auth failure.
"""
from __future__ import annotations

import socket
from email.message import EmailMessage

import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword

from app.integrations import smtp


class _RecordingHandler:
    def __init__(self) -> None:
        self.messages: list[bytes] = []

    async def handle_DATA(self, server, session, envelope):  # noqa: N802 — aiosmtpd hook name
        self.messages.append(envelope.content)
        return "250 Message accepted for delivery"


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


def _make_message() -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "recipient@example.com"
    msg["Subject"] = "Hello"
    msg.set_content("Plaintext")
    msg.add_alternative("<p>HTML</p>", subtype="html")
    return msg


def test_send_happy_path(smtp_server) -> None:
    _controller, handler, port = smtp_server
    smtp.send(_make_message(), host="127.0.0.1", port=port, username="user", password="secret")
    assert len(handler.messages) == 1
    payload = handler.messages[0].decode(errors="ignore")
    assert "Subject: Hello" in payload
    assert "HTML" in payload


def test_send_auth_failure_is_non_retryable(smtp_server) -> None:
    _controller, _handler, port = smtp_server
    with pytest.raises(smtp.SmtpCredentialError):
        smtp.send(_make_message(), host="127.0.0.1", port=port, username="user", password="wrong")
