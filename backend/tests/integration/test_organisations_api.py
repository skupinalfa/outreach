from fastapi.testclient import TestClient


def test_requires_authentication(app_client: TestClient) -> None:
    response = app_client.post("/api/v1/organisations", json={"name": "Acme"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_create_and_get(authed: TestClient) -> None:
    response = authed.post(
        "/api/v1/organisations",
        json={"name": "Acme GmbH", "domain": "acme.de"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Acme GmbH"
    assert body["domain"] == "acme.de"
    org_id = body["id"]

    fetched = authed.get(f"/api/v1/organisations/{org_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == org_id


def test_duplicate_name_returns_conflict(authed: TestClient) -> None:
    authed.post("/api/v1/organisations", json={"name": "Beta"})
    response = authed.post("/api/v1/organisations", json={"name": "beta"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_delete_cascades_contacts(authed: TestClient) -> None:
    """FR-001: deleting an organisation cascades to its contacts (and their drafts,
    sent_messages, todos via the child FKs). Detailed cascade coverage lives in
    test_organisations_delete_api.py; this smoke check just confirms the DELETE now
    returns 204 with a contact present."""
    org = authed.post("/api/v1/organisations", json={"name": "Gamma"}).json()
    contact = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org["id"],
            "first_name": "Max",
            "last_name": "Müller",
        },
    )
    assert contact.status_code == 201, contact.text

    response = authed.delete(f"/api/v1/organisations/{org['id']}")
    assert response.status_code == 204

    # The cascade removed the contact too — fetching it now yields 404.
    assert authed.get(f"/api/v1/contacts/{contact.json()['id']}").status_code == 404
