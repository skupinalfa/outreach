"""GET /api/v1/contacts — organisation_id + status filters, name/email search, pagination."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.contact import Contact, ContactStatus


def _org(authed: TestClient, name: str) -> int:
    return authed.post("/api/v1/organisations", json={"name": name}).json()["id"]


def _contact(authed: TestClient, org_id: int, first: str, last: str, email: str | None = None) -> int:
    body = {"organisation_id": org_id, "first_name": first, "last_name": last}
    if email:
        body["email"] = email
    return authed.post("/api/v1/contacts", json=body).json()["id"]


def _set_status(session_factory, contact_id: int, status: ContactStatus) -> None:
    with session_factory() as session:
        session.get(Contact, contact_id).status = status
        session.commit()


def test_filter_by_organisation(authed: TestClient) -> None:
    a = _org(authed, "Acme")
    b = _org(authed, "Beta")
    _contact(authed, a, "A", "One")
    _contact(authed, a, "A", "Two")
    _contact(authed, b, "B", "One")

    body = authed.get("/api/v1/contacts", params={"organisation_id": a}).json()
    assert body["total"] == 2
    assert {c["organisation_id"] for c in body["items"]} == {a}


def test_filter_by_status(authed: TestClient, session_factory) -> None:
    org_id = _org(authed, "Acme")
    c_enriched = _contact(authed, org_id, "A", "One")
    _contact(authed, org_id, "B", "Two")  # stays NEW
    _set_status(session_factory, c_enriched, ContactStatus.ENRICHED)

    body = authed.get("/api/v1/contacts", params={"status": "enriched"}).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == c_enriched


def test_search_name_or_email(authed: TestClient) -> None:
    org_id = _org(authed, "Acme")
    _contact(authed, org_id, "Max", "Müller", "max@acme.com")
    _contact(authed, org_id, "Ana", "Ramírez", "ana@acme.com")

    body = authed.get("/api/v1/contacts", params={"q": "MÜLL"}).json()
    assert body["total"] == 1
    assert body["items"][0]["last_name"] == "Müller"

    body = authed.get("/api/v1/contacts", params={"q": "ana@"}).json()
    assert body["total"] == 1
    assert body["items"][0]["first_name"] == "Ana"


def test_filters_compose(authed: TestClient, session_factory) -> None:
    a = _org(authed, "Acme")
    b = _org(authed, "Beta")
    c_a_enriched = _contact(authed, a, "A", "One")
    _contact(authed, a, "A", "Two")  # NEW
    c_b_enriched = _contact(authed, b, "B", "Three")
    _set_status(session_factory, c_a_enriched, ContactStatus.ENRICHED)
    _set_status(session_factory, c_b_enriched, ContactStatus.ENRICHED)

    body = authed.get(
        "/api/v1/contacts",
        params={"organisation_id": a, "status": "enriched"},
    ).json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == c_a_enriched


def test_pagination(authed: TestClient) -> None:
    org_id = _org(authed, "Acme")
    for i in range(4):
        _contact(authed, org_id, f"F{i}", f"L{i:02d}")
    body = authed.get("/api/v1/contacts", params={"limit": 2, "offset": 1}).json()
    assert body["total"] == 4
    assert len(body["items"]) == 2
    assert body["items"][0]["last_name"] == "L01"
