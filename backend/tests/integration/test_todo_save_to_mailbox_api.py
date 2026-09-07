"""Contract test — POST /api/v1/todos/{id}/save-to-mailbox (US3, FR-045..FR-049).

Verifies:
- Happy path: uploads to the resolved Drafts folder, marks todo `done` with
  `completed_via='mailbox_stored'`, records `draft_stored_in_mailbox` + `todo_completed`
  activity events, does NOT auto-schedule a follow-up (FR-048), returns the documented
  response shape.
- Error branches: credential_not_set (400), todo_not_actionable (409), imap_error (502),
  imap_drafts_not_found (502), mailbox_store_conflict (409). All persist a
  `mailbox_store_failed` activity event.
- Replace-in-place: a second save on the same draft version calls `replace_previous` and
  reports `replaced_previous=true`.

The IMAP wire behaviour is monkeypatched — this test asserts endpoint contract + service
orchestration, not the IMAP transport. Wire behaviour is covered by the folder-resolver
unit test and the live-integration test.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.integrations import imap as imap_integration
from app.integrations.imap import (
    IMAPCredentialError,
    IMAPDraftsNotFoundError,
    IMAPError,
    IMAPStoreConflictError,
)
from app.models.activity_event import ActivityEvent, ActivityEventType
from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.settings import Settings as SettingsRow
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType
from app.security import secrets as secret_helpers


def _seed_todo_and_draft(session_factory) -> int:
    """Create a fully-configured send-todo + draft for a contact. Returns the todo id."""
    with session_factory() as s:
        # IMAP + sender identity — required for the endpoint.
        row = s.get(SettingsRow, 1)
        row.imap_host = "imap.example"
        row.imap_port = 993
        row.imap_username_ct = secret_helpers.encrypt("u")
        row.imap_password_ct = secret_helpers.encrypt("p")
        row.imap_use_tls = True
        row.sender_email = "sender@example.com"
        row.sender_display_name = "Alfred"

        org = Organisation(name="Acme", domain="acme.example")
        s.add(org)
        s.flush()

        contact = Contact(
            organisation_id=org.id,
            first_name="Max",
            last_name="Mustermann",
            email="max@acme.example",
            status=ContactStatus.ENRICHED,
        )
        s.add(contact)
        s.flush()

        template = s.execute(select(Template).limit(1)).scalar_one()
        prompt = s.execute(select(Prompt).limit(1)).scalar_one()
        draft = Draft(
            contact_id=contact.id,
            template_id=template.id,
            template_body_snapshot=template.body,
            prompt_id=prompt.id,
            prompt_text_snapshot=prompt.text,
            subject="Hallo",
            body="Guten Tag",
        )
        s.add(draft)
        s.flush()

        todo = Todo(
            type=TodoType.SEND,
            title=f"Send to {contact.first_name} {contact.last_name}",
            contact_id=contact.id,
            draft_id=draft.id,
            due_at=datetime.now(UTC),
            status=TodoStatus.OPEN,
        )
        s.add(todo)
        s.commit()
        return todo.id


class _FakeIMAP:
    """Bare-minimum stand-in — the resolver and append are monkeypatched separately."""


def _mock_imap_success(monkeypatch: pytest.MonkeyPatch, *, folder: str = "Drafts", uid: int = 42) -> None:
    from contextlib import contextmanager

    @contextmanager
    def _fake_connect(cfg):
        yield _FakeIMAP()

    monkeypatch.setattr(imap_integration, "connect", _fake_connect)
    monkeypatch.setattr(
        imap_integration, "resolve_drafts_folder", lambda conn, **kw: (folder, True)
    )
    monkeypatch.setattr(imap_integration, "append_draft", lambda conn, folder, msg: uid)
    monkeypatch.setattr(imap_integration, "replace_previous", lambda conn, folder, prev_uid: None)


def test_save_to_mailbox_happy_path(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    todo_id = _seed_todo_and_draft(session_factory)
    _mock_imap_success(monkeypatch)

    response = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "Edited subject", "body": "Edited body"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # Response shape per contracts/api.md.
    assert set(body.keys()) == {"todo", "draft", "mailbox", "replaced_previous"}
    assert body["mailbox"]["folder"] == "Drafts"
    assert body["mailbox"]["uid"] == 42
    assert body["todo"]["status"] == "done"
    assert body["todo"]["completed_via"] == "mailbox_stored"
    assert body["draft"]["mailbox_folder"] == "Drafts"
    assert body["draft"]["mailbox_uid"] == 42
    assert body["replaced_previous"] is False

    with session_factory() as s:
        events = s.execute(
            select(ActivityEvent).order_by(ActivityEvent.occurred_at)
        ).scalars().all()
        types = [e.event_type for e in events]
        assert ActivityEventType.DRAFT_STORED_IN_MAILBOX in types
        assert ActivityEventType.TODO_COMPLETED in types
        # FR-048 — no follow-up scheduling from a save-to-mailbox.
        assert ActivityEventType.FOLLOW_UP_SCHEDULED not in types
        # No follow-up todo row either.
        follow_up_todos = s.execute(
            select(Todo).where(Todo.type == TodoType.FOLLOW_UP)
        ).scalars().all()
        assert follow_up_todos == []


def test_save_to_mailbox_replace_in_place_on_second_call(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    todo_id = _seed_todo_and_draft(session_factory)
    _mock_imap_success(monkeypatch, uid=100)

    first = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "v1", "body": "v1"},
    )
    assert first.status_code == 200

    # Reopen the todo — save-to-mailbox marks it done, so we simulate the operator
    # editing again by reopening. (Real workflow uses draft regeneration for a
    # second version, which resets mailbox_uid — verified in generation tests.)
    with session_factory() as s:
        todo = s.get(Todo, todo_id)
        todo.status = TodoStatus.OPEN
        todo.completed_at = None
        todo.completed_via = None
        s.commit()

    replace_calls: list[tuple[str, int]] = []

    def _fake_replace(conn, folder, prev_uid):
        replace_calls.append((folder, prev_uid))

    monkeypatch.setattr(imap_integration, "replace_previous", _fake_replace)
    monkeypatch.setattr(imap_integration, "append_draft", lambda conn, folder, msg: 200)

    second = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "v2", "body": "v2"},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["replaced_previous"] is True
    assert body["mailbox"]["uid"] == 200
    assert replace_calls == [("Drafts", 100)]


def test_save_to_mailbox_credential_not_set_when_imap_missing(
    authed: TestClient, session_factory
) -> None:
    with session_factory() as s:
        org = Organisation(name="X")
        s.add(org)
        s.flush()
        contact = Contact(
            organisation_id=org.id, first_name="A", last_name="B", email="a@x.example"
        )
        s.add(contact)
        s.flush()
        template = s.execute(select(Template).limit(1)).scalar_one()
        prompt = s.execute(select(Prompt).limit(1)).scalar_one()
        draft = Draft(
            contact_id=contact.id,
            template_id=template.id,
            template_body_snapshot=template.body,
            prompt_id=prompt.id,
            prompt_text_snapshot=prompt.text,
            subject="hi",
            body="bye",
        )
        s.add(draft)
        s.flush()
        todo = Todo(
            type=TodoType.SEND,
            title="send",
            contact_id=contact.id,
            draft_id=draft.id,
            due_at=datetime.now(UTC),
            status=TodoStatus.OPEN,
        )
        s.add(todo)
        s.commit()
        todo_id = todo.id

    response = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "s", "body": "b"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"


def test_save_to_mailbox_todo_not_actionable_when_todo_is_done(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    todo_id = _seed_todo_and_draft(session_factory)
    with session_factory() as s:
        todo = s.get(Todo, todo_id)
        todo.status = TodoStatus.DONE
        s.commit()

    response = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "s", "body": "b"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "todo_not_actionable"


def test_save_to_mailbox_imap_error_502_and_records_failure(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    todo_id = _seed_todo_and_draft(session_factory)
    _mock_imap_success(monkeypatch)

    def _raise(conn, folder, msg):
        raise IMAPError("APPEND: 550 quota exceeded")

    monkeypatch.setattr(imap_integration, "append_draft", _raise)

    response = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "s", "body": "b"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "imap_error"

    with session_factory() as s:
        events = s.execute(select(ActivityEvent)).scalars().all()
        assert any(
            e.event_type == ActivityEventType.MAILBOX_STORE_FAILED for e in events
        )
        # Todo remains open.
        todo = s.get(Todo, todo_id)
        assert todo.status == TodoStatus.OPEN
        assert todo.completed_via is None


def test_save_to_mailbox_drafts_not_found_502(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    todo_id = _seed_todo_and_draft(session_factory)
    from contextlib import contextmanager

    @contextmanager
    def _fake_connect(cfg):
        yield _FakeIMAP()

    def _no_drafts(conn, **kw):
        raise IMAPDraftsNotFoundError("no drafts folder resolved")

    monkeypatch.setattr(imap_integration, "connect", _fake_connect)
    monkeypatch.setattr(imap_integration, "resolve_drafts_folder", _no_drafts)

    response = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "s", "body": "b"},
    )
    assert response.status_code == 502
    err = response.json()["error"]
    assert err["code"] == "imap_drafts_not_found"
    assert "tried_folders" in err["detail"]


def test_save_to_mailbox_credential_error_from_imap_boundary_returns_400(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    todo_id = _seed_todo_and_draft(session_factory)
    from contextlib import contextmanager

    @contextmanager
    def _fake_connect(cfg):
        # Simulate auth failure surfaced from the IMAP boundary
        raise IMAPCredentialError("IMAP authentication failed: bad login")

    monkeypatch.setattr(imap_integration, "connect", _fake_connect)

    response = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "s", "body": "b"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "credential_not_set"


def test_save_to_mailbox_store_conflict_returns_409(
    authed: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    todo_id = _seed_todo_and_draft(session_factory)

    # Seed a previous mailbox coordinate on the draft so replace_previous is invoked.
    with session_factory() as s:
        draft = s.execute(select(Draft)).scalar_one()
        draft.mailbox_folder = "Drafts"
        draft.mailbox_uid = 77
        draft.mailbox_stored_at = datetime.now(UTC)
        s.commit()

    _mock_imap_success(monkeypatch)

    def _conflict(conn, folder, prev_uid):
        raise IMAPStoreConflictError("server does not advertise UIDPLUS")

    monkeypatch.setattr(imap_integration, "replace_previous", _conflict)

    response = authed.post(
        f"/api/v1/todos/{todo_id}/save-to-mailbox",
        json={"subject": "s", "body": "b"},
    )
    assert response.status_code == 409
    err = response.json()["error"]
    assert err["code"] == "mailbox_store_conflict"
    assert err["detail"]["folder"] == "Drafts"
