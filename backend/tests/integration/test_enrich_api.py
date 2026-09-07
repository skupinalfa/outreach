"""Integration test for POST /contacts/{id}/enrich.

Hunter's HTTP surface is intercepted by monkey-patching the boundary module so this test
does not need live credentials or a cassette. The wire-level Hunter contract is exercised
separately in `tests/contract/test_hunter.py` (vcrpy).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.integrations import hunter
from app.models.contact import Contact
from app.models.organisation import Organisation
from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers


def _make_lead(client: TestClient) -> int:
    org = client.post("/api/v1/organisations", json={"name": "Stripe"}).json()
    contact = client.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org["id"],
            "first_name": "Patrick",
            "last_name": "Collison",
            "gender": "m",
        },
    ).json()
    return contact["id"]


def _seed_hunter_key(session_factory) -> None:
    with session_factory() as session:
        row = session.get(SettingsRow, 1)
        row.hunter_api_key_ct = secret_helpers.encrypt("test-hunter-key")
        session.commit()


def test_enrich_success_sets_email_and_status(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_hunter_key(session_factory)
    contact_id = _make_lead(authed)

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

    response = authed.post(f"/api/v1/contacts/{contact_id}/enrich")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "patrick@stripe.com"
    assert body["position"] == "CEO"
    assert body["status"] == "enriched"
    assert body["last_enrichment_error"] is None


def test_enrich_credential_missing_returns_400(authed: TestClient) -> None:
    contact_id = _make_lead(authed)
    response = authed.post(f"/api/v1/contacts/{contact_id}/enrich")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"


def test_enrich_hunter_error_persists_reason(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_hunter_key(session_factory)
    contact_id = _make_lead(authed)

    def _boom(*_args, **_kwargs):
        raise hunter.HunterError("upstream 503 after retries")

    monkeypatch.setattr(hunter, "resolve_domain", _boom)

    response = authed.post(f"/api/v1/contacts/{contact_id}/enrich")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "hunter_error"

    fetched = authed.get(f"/api/v1/contacts/{contact_id}").json()
    assert fetched["last_enrichment_error"] is not None
    assert "503" in fetched["last_enrichment_error"]


def test_manual_email_survives_re_enrichment(
    authed: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-005: enrichment MUST NOT overwrite an email the operator has set by hand.

    Seed a contact whose email is a manual value; run enrichment with a stubbed Hunter
    that would return a *different* email; assert the manual value survives and that
    the surrounding enrichment side-effects (last_enriched_at, org.domain if empty)
    still happen.
    """
    _seed_hunter_key(session_factory)

    # Fresh org (no domain) + contact with a manually-set email.
    with session_factory() as session:
        org = Organisation(name="Stripe")
        session.add(org)
        session.flush()
        contact = Contact(
            organisation_id=org.id,
            first_name="Patrick",
            last_name="Collison",
            email="patrick+manual@stripe.com",
        )
        session.add(contact)
        session.commit()
        contact_id = contact.id
        org_id = org.id

    monkeypatch.setattr(hunter, "resolve_domain", lambda company, api_key: "stripe.com")
    monkeypatch.setattr(
        hunter,
        "find_email",
        lambda first, last, domain, api_key: hunter.EmailFinderResult(
            email="hunter-found@stripe.com",  # deliberately different from the manual value
            domain=domain,
            score=99,
            position="CEO",
            verification_status="valid",
        ),
    )

    response = authed.post(f"/api/v1/contacts/{contact_id}/enrich")
    assert response.status_code == 200, response.text
    body = response.json()

    # Manual email survives.
    assert body["email"] == "patrick+manual@stripe.com"
    # Position was empty → still filled from Hunter (partial refresh is allowed).
    assert body["position"] == "CEO"
    # Enrichment audit still updated.
    assert body["last_enriched_at"] is not None
    assert body["last_enrichment_error"] is None

    # Org.domain was empty → refreshed from Hunter.
    with session_factory() as session:
        org = session.get(Organisation, org_id)
        assert org.domain == "stripe.com"
