"""Hunter.io boundary — domain-finder + email-finder.

Retries transient failures (429, 5xx) up to 3 times with 200/400/800 ms backoff.
Non-retryable failures raise `HunterError` (upstream) or `HunterCredentialError`
(missing/invalid API key).
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.logging import get_logger

_BASE_URL = "https://api.hunter.io/v2"
_TIMEOUT = 15.0

log = get_logger("hunter")


class HunterError(Exception):
    """Non-retryable Hunter failure (4xx other than 401/429, unexpected shape)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class HunterCredentialError(HunterError):
    """Hunter rejected the API key (401) or key not configured."""


class _RetryableHunterError(Exception):
    """Internal marker: 429 or 5xx — worth retrying."""


@dataclass(frozen=True)
class EmailFinderResult:
    email: str | None
    domain: str | None
    score: int | None
    position: str | None
    verification_status: str | None


def _retry():
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=0.8),
        retry=retry_if_exception_type(_RetryableHunterError),
    )


def _get(endpoint: str, params: dict, api_key: str) -> dict:
    if not api_key:
        raise HunterCredentialError("Hunter API key is not configured.")

    @_retry()
    def _do() -> dict:
        response = httpx.get(
            f"{_BASE_URL}/{endpoint}",
            params={**params, "api_key": api_key},
            timeout=_TIMEOUT,
        )
        if response.status_code == 401:
            raise HunterCredentialError("Hunter rejected the API key.")
        if response.status_code == 429 or 500 <= response.status_code < 600:
            raise _RetryableHunterError(f"Hunter transient error: {response.status_code}")
        if response.status_code != 200:
            try:
                body = response.json()
            except ValueError:
                body = {}
            errors = body.get("errors", [{}])
            detail = errors[0].get("details") if errors else response.text
            raise HunterError(f"Hunter {endpoint} error: {detail}", status=response.status_code)
        return response.json()

    try:
        return _do()
    except RetryError as exc:
        raise HunterError("Hunter transient error after retries.") from exc


def resolve_domain(company: str, api_key: str) -> str | None:
    """Resolve a company name to its most likely domain. Returns None if unresolved."""
    if len(company) < 3:
        raise HunterError("Domain finder requires at least 3 characters.")

    data = _get(
        "domain-finder",
        {"company": company, "limit": 1, "perfect_match": "true"},
        api_key,
    )
    items = data.get("data") or []
    if isinstance(items, dict):
        return items.get("domain")
    if items:
        return items[0].get("domain")
    return None


def find_email(
    first_name: str,
    last_name: str,
    domain: str,
    api_key: str,
) -> EmailFinderResult:
    """Look up a work email for a person at a domain."""
    data = _get(
        "email-finder",
        {"first_name": first_name, "last_name": last_name, "domain": domain},
        api_key,
    ).get("data", {})

    verification = data.get("verification") or {}
    return EmailFinderResult(
        email=data.get("email"),
        domain=data.get("domain"),
        score=data.get("score"),
        position=data.get("position"),
        verification_status=verification.get("status"),
    )
