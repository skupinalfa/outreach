"""DELETE /api/v1/organisations/{id} — 409 while contacts exist, 204 once empty."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_delete_blocks_when_contacts_exist_and_unblocks_after(authed: TestClient) -> None:
    org = authed.post("/api/v1/organisations", json={"name": "Acme"}).json()
    contact = authed.post(
        "/api/v1/contacts",
        json={"organisation_id": org["id"], "first_name": "A", "last_name": "B"},
    ).json()

    blocked = authed.delete(f"/api/v1/organisations/{org['id']}")
    assert blocked.status_code == 409
    body = blocked.json()
    assert body["error"]["code"] == "conflict"
    assert "contact" in body["error"]["message"].lower()

    # Removing the last contact should unblock deletion.
    authed.delete(f"/api/v1/contacts/{contact['id']}")
    allowed = authed.delete(f"/api/v1/organisations/{org['id']}")
    assert allowed.status_code == 204


def test_delete_unknown_org_returns_404(authed: TestClient) -> None:
    response = authed.delete("/api/v1/organisations/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
