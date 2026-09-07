"""GET /todos includes the on-render `scheduled -> open` promotion."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models.contact import Contact
from app.models.organisation import Organisation
from app.models.todo import Todo, TodoStatus, TodoType


def _seed_contact(session_factory) -> int:
    with session_factory() as session:
        org = Organisation(name="Acme")
        session.add(org)
        session.flush()
        contact = Contact(
            organisation_id=org.id,
            first_name="A",
            last_name="B",
        )
        session.add(contact)
        session.commit()
        return contact.id


def _make_todo(
    session_factory, contact_id: int, status: TodoStatus, due_at: datetime
) -> int:
    with session_factory() as session:
        todo = Todo(
            type=TodoType.FOLLOW_UP,
            title="follow up",
            contact_id=contact_id,
            due_at=due_at,
            status=status,
        )
        session.add(todo)
        session.commit()
        return todo.id


def test_list_returns_todos_and_paginates(authed: TestClient, session_factory) -> None:
    contact_id = _seed_contact(session_factory)
    for _ in range(3):
        _make_todo(
            session_factory,
            contact_id,
            TodoStatus.OPEN,
            datetime.now(UTC),
        )
    response = authed.get("/api/v1/todos")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_scheduled_todos_get_promoted_on_render(
    authed: TestClient, session_factory
) -> None:
    contact_id = _seed_contact(session_factory)
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(days=1)
    overdue = _make_todo(session_factory, contact_id, TodoStatus.SCHEDULED, past)
    later = _make_todo(session_factory, contact_id, TodoStatus.SCHEDULED, future)

    authed.get("/api/v1/todos")  # triggers promotion

    with session_factory() as session:
        overdue_todo = session.get(Todo, overdue)
        later_todo = session.get(Todo, later)
        assert overdue_todo.status == TodoStatus.OPEN
        assert later_todo.status == TodoStatus.SCHEDULED


def test_status_filter(authed: TestClient, session_factory) -> None:
    contact_id = _seed_contact(session_factory)
    _make_todo(
        session_factory,
        contact_id,
        TodoStatus.OPEN,
        datetime.now(UTC),
    )
    _make_todo(
        session_factory,
        contact_id,
        TodoStatus.DONE,
        datetime.now(UTC),
    )
    body = authed.get("/api/v1/todos", params={"status": "open"}).json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "open"
