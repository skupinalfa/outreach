"""OpenAI boundary — Responses API with the `web_search` tool.

Retries on `RateLimitError`, `APITimeoutError`, `APIConnectionError`, and 5xx status codes
(3 attempts, 200/400/800 ms backoff). Non-retryable failures raise `OpenAIError`;
parse failures on the response text raise `OpenAIParseError` (defined in `services/openai_parser`).
"""
from __future__ import annotations

import openai
from openai import OpenAI
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.logging import get_logger

log = get_logger("openai")


class OpenAIError(Exception):
    """Non-retryable OpenAI failure."""


class OpenAICredentialError(OpenAIError):
    """API key missing or rejected by OpenAI (401)."""


class _RetryableOpenAIError(Exception):
    """Internal marker: rate limit, timeout, connection, or 5xx."""


def _extract_text(response: object) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    parts: list[str] = []
    for entry in getattr(response, "output", []) or []:
        if getattr(entry, "type", None) != "message":
            continue
        content = getattr(entry, "content", None)
        if isinstance(content, str):
            parts.append(content)
            continue
        for chunk in content or []:
            if getattr(chunk, "type", None) == "output_text":
                chunk_text = getattr(chunk, "text", None)
                if chunk_text:
                    parts.append(chunk_text)
    return "\n".join(parts)


def _retry():
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=0.8),
        retry=retry_if_exception_type(_RetryableOpenAIError),
    )


def generate(
    prompt: str,
    api_key: str,
    model: str = "gpt-5.6-luna",
    max_tokens: int = 10_000,
) -> str:
    """Blocking call to `responses.create` with the web_search tool. Returns raw output text."""
    if not api_key:
        raise OpenAICredentialError("OpenAI API key is not configured.")

    @_retry()
    def _do() -> str:
        try:
            with OpenAI(api_key=api_key) as client:
                response = client.responses.create(
                    model=model,
                    input=prompt,
                    tools=[{"type": "web_search"}],
                    max_output_tokens=max_tokens,
                )
            return _extract_text(response)
        except openai.RateLimitError as exc:
            raise _RetryableOpenAIError(f"rate limit: {exc}") from exc
        except openai.APITimeoutError as exc:
            raise _RetryableOpenAIError(f"timeout: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise _RetryableOpenAIError(f"connection: {exc}") from exc
        except openai.APIStatusError as exc:
            status = exc.status_code
            if status is not None and 500 <= status < 600:
                raise _RetryableOpenAIError(f"upstream {status}: {exc}") from exc
            if status == 401:
                raise OpenAICredentialError("OpenAI rejected the API key.") from exc
            raise OpenAIError(f"OpenAI client error ({status}): {exc}") from exc

    try:
        return _do()
    except RetryError as exc:
        raise OpenAIError("OpenAI transient error after retries.") from exc


def test_credentials(api_key: str) -> None:
    """Cheap authentication probe. Raises `OpenAICredentialError` / `OpenAIError`."""
    if not api_key:
        raise OpenAICredentialError("OpenAI API key is not configured.")
    try:
        with OpenAI(api_key=api_key) as client:
            # `models.list` is the standard live-auth probe and is billed at $0.
            client.models.list()
    except openai.AuthenticationError as exc:
        raise OpenAICredentialError("OpenAI rejected the API key.") from exc
    except openai.APIStatusError as exc:
        if exc.status_code == 401:
            raise OpenAICredentialError("OpenAI rejected the API key.") from exc
        raise OpenAIError(f"OpenAI probe failed ({exc.status_code}): {exc}") from exc
    except (openai.APIConnectionError, openai.APITimeoutError) as exc:
        raise OpenAIError(f"OpenAI probe network error: {exc}") from exc
