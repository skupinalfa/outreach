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


def test_delete_blocks_when_contacts_exist(authed: TestClient) -> None:
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

    blocked = authed.delete(f"/api/v1/organisations/{org['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "conflict"

    authed.delete(f"/api/v1/contacts/{contact.json()['id']}")
    allowed = authed.delete(f"/api/v1/organisations/{org['id']}")
    assert allowed.status_code == 204
