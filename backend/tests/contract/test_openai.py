"""Contract test for the OpenAI `responses.create` endpoint with the `web_search` tool.

Recorded once against the real service. Skipped if the cassette is not present and
`VCR_RECORD` is not set.
"""
from __future__ import annotations

import os
import pathlib

import pytest

from app.integrations import openai_client
from app.services.openai_parser import parse_openai_response

CASSETTE_DIR = pathlib.Path(__file__).parent / "cassettes"


def _cassette_ready(name: str) -> bool:
    return (CASSETTE_DIR / f"{name}.yaml").exists() or os.environ.get("VCR_RECORD") == "1"


def test_generate_returns_parseable_payload(cassette: pathlib.Path) -> None:
    if not _cassette_ready(cassette.stem):
        pytest.skip(f"No cassette {cassette.name}; set VCR_RECORD=1 with an OPENAI_API_KEY.")

    api_key = os.environ.get("OPENAI_API_KEY", "recorded")
    prompt = (
        "Recherchiere Stripe unter stripe.com. Schreibe eine kurze E-Mail an Collison. "
        'Antwort als JSON: {"subject":"...","text":"..."}.'
    )
    raw = openai_client.generate(prompt, api_key=api_key, max_tokens=500)
    subject, body = parse_openai_response(raw)
    assert subject.strip()
    assert body.strip()
