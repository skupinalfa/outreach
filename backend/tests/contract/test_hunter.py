"""Contract tests for the Hunter.io HTTP surface we depend on.

Recorded once against the real service via `VCR_RECORD=1` with a live API key. Replayed
against the checked-in cassette in CI. If the cassette is missing and no key is available,
the test is skipped so CI doesn't hit the network by accident.
"""
from __future__ import annotations

import os
import pathlib

import pytest

from app.integrations import hunter

CASSETTE_DIR = pathlib.Path(__file__).parent / "cassettes"


def _cassette_ready(name: str) -> bool:
    return (CASSETTE_DIR / f"{name}.yaml").exists() or os.environ.get("VCR_RECORD") == "1"


def test_resolve_domain(cassette: pathlib.Path) -> None:
    if not _cassette_ready(cassette.stem):
        pytest.skip(f"No cassette {cassette.name}; set VCR_RECORD=1 with a HUNTER_API_KEY to record.")
    api_key = os.environ.get("HUNTER_API_KEY", "recorded")
    domain = hunter.resolve_domain("Stripe", api_key=api_key)
    assert domain is not None
    assert "." in domain


def test_find_email(cassette: pathlib.Path) -> None:
    if not _cassette_ready(cassette.stem):
        pytest.skip(f"No cassette {cassette.name}; set VCR_RECORD=1 with a HUNTER_API_KEY to record.")
    api_key = os.environ.get("HUNTER_API_KEY", "recorded")
    result = hunter.find_email("Patrick", "Collison", "stripe.com", api_key=api_key)
    assert result.domain is None or isinstance(result.domain, str)
