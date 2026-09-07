"""GET /api/v1/organisations — list, case-insensitive search, and pagination."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(authed: TestClient, names: list[str]) -> None:
    for name in names:
        authed.post("/api/v1/organisations", json={"name": name})


def test_lists_alphabetically_and_reports_total(authed: TestClient) -> None:
    _seed(authed, ["Charlie AG", "Alpha Ltd", "Bravo GmbH"])
    response = authed.get("/api/v1/organisations")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [o["name"] for o in body["items"]] == ["Alpha Ltd", "Bravo GmbH", "Charlie AG"]


def test_search_is_case_insensitive_across_name_and_domain(authed: TestClient) -> None:
    authed.post("/api/v1/organisations", json={"name": "Stripe", "domain": "stripe.com"})
    authed.post("/api/v1/organisations", json={"name": "Acme", "domain": "acme.de"})
    authed.post("/api/v1/organisations", json={"name": "Beta"})

    body = authed.get("/api/v1/organisations", params={"q": "STRIP"}).json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Stripe"

    body = authed.get("/api/v1/organisations", params={"q": "acme.de"}).json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Acme"


def test_pagination_limit_and_offset(authed: TestClient) -> None:
    _seed(authed, [f"Company {i:02d}" for i in range(5)])
    body = authed.get("/api/v1/organisations", params={"limit": 2, "offset": 2}).json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "Company 02"
    assert body["items"][1]["name"] == "Company 03"


def test_organisation_contacts_endpoint(authed: TestClient) -> None:
    org = authed.post("/api/v1/organisations", json={"name": "Acme"}).json()
    other_org = authed.post("/api/v1/organisations", json={"name": "Beta"}).json()
    for last in ("Müller", "Aardvark"):
        authed.post(
            "/api/v1/contacts",
            json={"organisation_id": org["id"], "first_name": "A", "last_name": last},
        )
    authed.post(
        "/api/v1/contacts",
        json={"organisation_id": other_org["id"], "first_name": "Z", "last_name": "Z"},
    )

    response = authed.get(f"/api/v1/organisations/{org['id']}/contacts")
    assert response.status_code == 200
    contacts = response.json()
    assert len(contacts) == 2
    assert [c["last_name"] for c in contacts] == ["Aardvark", "Müller"]
