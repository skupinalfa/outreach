from fastapi.testclient import TestClient


def _new_org(authed: TestClient, name: str = "Acme") -> int:
    org = authed.post("/api/v1/organisations", json={"name": name})
    return org.json()["id"]


def test_create_requires_existing_organisation(authed: TestClient) -> None:
    response = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": 999999,
            "first_name": "Max",
            "last_name": "Müller",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_create_and_patch(authed: TestClient) -> None:
    org_id = _new_org(authed)
    created = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org_id,
            "first_name": "Max",
            "last_name": "Müller",
            "gender": "m",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "new"
    assert body["latest_draft"] is None

    patched = authed.patch(
        f"/api/v1/contacts/{body['id']}",
        json={"position": "CTO"},
    )
    assert patched.status_code == 200
    assert patched.json()["position"] == "CTO"


def test_duplicate_email_in_same_org_conflicts(authed: TestClient) -> None:
    org_id = _new_org(authed, name="Delta")
    authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org_id,
            "first_name": "A",
            "last_name": "B",
            "email": "same@delta.com",
        },
    )
    dup = authed.post(
        "/api/v1/contacts",
        json={
            "organisation_id": org_id,
            "first_name": "C",
            "last_name": "D",
            "email": "SAME@delta.com",
        },
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"
