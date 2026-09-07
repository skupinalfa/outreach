"""SMTP boundary — sends a fully-composed EmailMessage over SSL/STARTTLS.

Retries transient failures (4xx SMTP codes, EOF, timeout) up to 3 times with 200/400/800 ms
backoff. Non-retryable failures raise `SmtpError`; auth failures raise `SmtpCredentialError`.
"""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.logging import get_logger

log = get_logger("smtp")


class SmtpError(Exception):
    """Non-retryable SMTP failure (permanent, 5xx SMTP or unexpected protocol error)."""


class SmtpCredentialError(SmtpError):
    """SMTP server rejected auth (535)."""


class _RetryableSmtpError(Exception):
    """Transient SMTP failure (4xx, connection reset, EOF)."""


def _retry():
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=0.8),
        retry=retry_if_exception_type(_RetryableSmtpError),
    )


def send(
    msg: EmailMessage,
    host: str,
    port: int,
    username: str,
    password: str,
) -> None:
    if not host or not port:
        raise SmtpCredentialError("SMTP host/port not configured.")
    if not username or not password:
        raise SmtpCredentialError("SMTP credentials not configured.")

    @_retry()
    def _do() -> None:
        try:
            if port == 465:
                with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as smtp:
                    smtp.login(username, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port) as smtp:
                    smtp.ehlo()
                    if smtp.has_extn("STARTTLS"):
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                    smtp.login(username, password)
                    smtp.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise SmtpCredentialError(f"SMTP authentication failed: {exc}") from exc
        except (smtplib.SMTPServerDisconnected, TimeoutError, ConnectionError) as exc:
            raise _RetryableSmtpError(f"SMTP transient: {exc}") from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise _RetryableSmtpError(f"SMTP 4xx: {exc}") from exc
            raise SmtpError(f"SMTP {exc.smtp_code}: {exc.smtp_error!r}") from exc
        except smtplib.SMTPException as exc:
            raise SmtpError(f"SMTP failure: {exc}") from exc

    try:
        _do()
    except RetryError as exc:
        raise SmtpError("SMTP transient failure after retries.") from exc


def test_credentials(host: str, port: int, username: str, password: str) -> None:
    """Connect + AUTH + QUIT, no message sent. Raises the same typed errors as `send`."""
    if not host or not port:
        raise SmtpCredentialError("SMTP host/port not configured.")
    if not username or not password:
        raise SmtpCredentialError("SMTP credentials not configured.")

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as smtp:
                smtp.login(username, password)
        else:
            with smtplib.SMTP(host, port) as smtp:
                smtp.ehlo()
                if smtp.has_extn("STARTTLS"):
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(username, password)
    except smtplib.SMTPAuthenticationError as exc:
        raise SmtpCredentialError(f"SMTP authentication failed: {exc}") from exc
    except (smtplib.SMTPServerDisconnected, TimeoutError, ConnectionError) as exc:
        raise SmtpError(f"Could not reach SMTP server: {exc}") from exc
    except smtplib.SMTPException as exc:
        raise SmtpError(f"SMTP failure: {exc}") from exc
