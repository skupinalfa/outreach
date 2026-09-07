"""Integration test for POST /api/v1/hunter/domain-lookup (FR-004a).

The Hunter HTTP surface is monkey-patched at the boundary — the wire-level Hunter
contract is exercised separately in tests/contract/test_hunter_domain_lookup.py.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.integrations import hunter
from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers


def _seed_hunter_key(session_factory) -> None:
    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        row.hunter_api_key_ct = secret_helpers.encrypt("test-hunter-key")
        session.commit()


def test_domain_lookup_hit_returns_domain(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_hunter_key(session_factory)
    monkeypatch.setattr(hunter, "resolve_domain", lambda company, api_key: "stripe.com")

    response = authed.post("/api/v1/hunter/domain-lookup", json={"company_name": "Stripe"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "stripe.com"
    assert body["source"] == "hunter"
    assert body["message"] is None


def test_domain_lookup_miss_returns_null_with_hint(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-004b: no-result is a soft failure, not a hard error — the operator must be able
    to type the domain by hand to unlock the gate."""
    _seed_hunter_key(session_factory)
    monkeypatch.setattr(hunter, "resolve_domain", lambda company, api_key: None)

    response = authed.post(
        "/api/v1/hunter/domain-lookup",
        json={"company_name": "Nonexistent-Zzz"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] is None
    assert body["source"] == "hunter"
    assert "Nonexistent-Zzz" in body["message"]
    assert "manually" in body["message"]


def test_domain_lookup_requires_auth(app_client: TestClient) -> None:
    response = app_client.post("/api/v1/hunter/domain-lookup", json={"company_name": "Stripe"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_domain_lookup_without_key_returns_credential_not_set(authed: TestClient) -> None:
    # No _seed_hunter_key() — the settings row's hunter_api_key_ct is left None.
    response = authed.post("/api/v1/hunter/domain-lookup", json={"company_name": "Stripe"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"


def test_domain_lookup_hunter_error_returns_502(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_hunter_key(session_factory)

    def _boom(*_args, **_kwargs):
        raise hunter.HunterError("upstream 503 after retries")

    monkeypatch.setattr(hunter, "resolve_domain", _boom)

    response = authed.post("/api/v1/hunter/domain-lookup", json={"company_name": "Stripe"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "hunter_error"


def test_domain_lookup_rejects_empty_company_name(authed: TestClient, session_factory) -> None:
    _seed_hunter_key(session_factory)
    response = authed.post("/api/v1/hunter/domain-lookup", json={"company_name": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
