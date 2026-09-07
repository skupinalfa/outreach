"""Contract tests for Hunter Domain Search — the wire behavior the FR-004a
"Look up domain" action depends on.

Two cassettes: (a) a domain hit for a known company ("Stripe"), (b) a miss for a
nonsense company name. Recorded once via `VCR_RECORD=1` with a live `HUNTER_API_KEY`;
replayed offline in CI. Missing cassette + no key → skipped (Constitution V).
"""
from __future__ import annotations

import os
import pathlib

import pytest

from app.integrations import hunter

CASSETTE_DIR = pathlib.Path(__file__).parent / "cassettes"


def _cassette_ready(name: str) -> bool:
    return (CASSETTE_DIR / f"{name}.yaml").exists() or os.environ.get("VCR_RECORD") == "1"


def test_domain_lookup_hit(cassette: pathlib.Path) -> None:
    if not _cassette_ready(cassette.stem):
        pytest.skip(f"No cassette {cassette.name}; set VCR_RECORD=1 with a HUNTER_API_KEY to record.")
    api_key = os.environ.get("HUNTER_API_KEY", "recorded")
    domain = hunter.resolve_domain("Stripe", api_key=api_key)
    assert domain is not None
    assert "." in domain


def test_domain_lookup_miss(cassette: pathlib.Path) -> None:
    """FR-004b: Hunter returning no domain for a bogus name must not raise —
    the wrapper returns None so the router can hand back the manual-fallback hint."""
    if not _cassette_ready(cassette.stem):
        pytest.skip(f"No cassette {cassette.name}; set VCR_RECORD=1 with a HUNTER_API_KEY to record.")
    api_key = os.environ.get("HUNTER_API_KEY", "recorded")
    domain = hunter.resolve_domain("Nonexistent-Company-Zzz-1234567", api_key=api_key)
    assert domain is None
