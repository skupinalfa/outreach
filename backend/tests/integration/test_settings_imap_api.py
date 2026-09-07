"""Contract test — Settings API IMAP extension (FR-050).

Verifies:
- PATCH /api/v1/settings accepts nested `imap.*` fields and Fernet-encrypts the secrets.
- GET /api/v1/settings exposes an `imap` block with *_set boolean flags — no plaintext.
- Changing imap_host / imap_username / imap_drafts_folder invalidates the detected-folder cache.
- POST /api/v1/settings/test/imap returns the resolved folder on success, an error message
  on failure, and 400 credential_not_set when the config is incomplete.

The IMAP connection itself is monkeypatched so the tests run without a real IMAP server;
wire behaviour is covered by the folder-resolver unit tests and the live-integration test.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.integrations import imap as imap_integration
from app.models.settings import Settings as SettingsRow
from app.security import secrets as secret_helpers


def test_get_settings_exposes_imap_block_with_no_plaintext(authed: TestClient) -> None:
    body = authed.get("/api/v1/settings").json()
    assert "imap" in body
    imap = body["imap"]
    assert set(imap.keys()) == {
        "host", "port", "username_set", "password_set", "use_tls",
        "drafts_folder", "drafts_folder_detected",
    }
    # None set on a fresh install; no plaintext keys leak in.
    assert imap["username_set"] is False
    assert imap["password_set"] is False
    for leaked in ("username", "password", "username_ct", "password_ct"):
        assert leaked not in imap


def test_patch_imap_fields_encrypts_and_persists(
    authed: TestClient, session_factory
) -> None:
    response = authed.patch(
        "/api/v1/settings",
        json={
            "imap": {
                "host": "imap.mailbox.org",
                "port": 993,
                "username": "u",
                "password": "p",
                "use_tls": True,
                "drafts_folder": None,
            }
        },
    )
    assert response.status_code == 200
    body = response.json()["imap"]
    assert body["host"] == "imap.mailbox.org"
    assert body["port"] == 993
    assert body["username_set"] is True
    assert body["password_set"] is True

    with session_factory() as s:
        row = s.get(SettingsRow, 1)
        assert row.imap_host == "imap.mailbox.org"
        assert row.imap_port == 993
        assert secret_helpers.decrypt(row.imap_username_ct) == "u"
        assert secret_helpers.decrypt(row.imap_password_ct) == "p"
        assert row.imap_use_tls is True


def test_changing_host_invalidates_detected_folder_cache(
    authed: TestClient, session_factory
) -> None:
    with session_factory() as s:
        row = s.get(SettingsRow, 1)
        row.imap_host = "imap.old.example"
        row.imap_drafts_folder_detected = "Drafts"
        s.commit()

    authed.patch("/api/v1/settings", json={"imap": {"host": "imap.new.example"}})

    with session_factory() as s:
        row = s.get(SettingsRow, 1)
        assert row.imap_host == "imap.new.example"
        assert row.imap_drafts_folder_detected is None


def test_test_imap_returns_400_when_credentials_missing(authed: TestClient) -> None:
    response = authed.post("/api/v1/settings/test/imap", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"


def test_test_imap_reports_resolved_folder_on_success(
    authed: TestClient, session_factory, monkeypatch
) -> None:
    with session_factory() as s:
        row = s.get(SettingsRow, 1)
        row.imap_host = "imap.example"
        row.imap_port = 993
        row.imap_username_ct = secret_helpers.encrypt("u")
        row.imap_password_ct = secret_helpers.encrypt("p")
        s.commit()

    monkeypatch.setattr(imap_integration, "test_credentials", lambda cfg: "Drafts")

    response = authed.post("/api/v1/settings/test/imap", json={})
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["resolved_drafts_folder"] == "Drafts"
    assert "Drafts" in body["message"]

    with session_factory() as s:
        row = s.get(SettingsRow, 1)
        assert row.imap_drafts_folder_detected == "Drafts"


def test_test_imap_returns_ok_false_on_credential_error(
    authed: TestClient, session_factory, monkeypatch
) -> None:
    with session_factory() as s:
        row = s.get(SettingsRow, 1)
        row.imap_host = "imap.example"
        row.imap_port = 993
        row.imap_username_ct = secret_helpers.encrypt("u")
        row.imap_password_ct = secret_helpers.encrypt("bad")
        s.commit()

    def _boom(cfg):
        raise imap_integration.IMAPCredentialError("authentication failed")

    monkeypatch.setattr(imap_integration, "test_credentials", _boom)

    response = authed.post("/api/v1/settings/test/imap", json={})
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["resolved_drafts_folder"] is None
    assert "authentication failed" in body["message"]
