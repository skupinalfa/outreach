"""DELETE /api/v1/organisations/{id} — cascades to contacts + drafts + sent_messages + todos.

Backs FR-001 (cascade), FR-027a (frontend enforces the confirmation dialog — server does
not re-prompt or block), and research.md R14. Supersedes the earlier
`test_delete_blocks_when_contacts_exist_and_unblocks_after` case which asserted a 409
block; that behaviour was inverted by the 2026-09-07 delete-addendum clarifications.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType


def _seed_full_tree(session_factory, org_name: str = "CascadeCo") -> int:
    """Seed one org + two contacts + drafts + sent_messages + open + scheduled todos.

    Returns the org id.
    """
    with session_factory() as session:
        template = session.execute(select(Template).limit(1)).scalar_one()
        prompt = session.execute(select(Prompt).limit(1)).scalar_one()

        org = Organisation(name=org_name)
        session.add(org)
        session.flush()

        contacts: list[Contact] = []
        for i in range(2):
            c = Contact(
                organisation_id=org.id,
                first_name=f"F{i}",
                last_name=f"L{i}",
                email=f"c{i}@cascade.co",
                status=ContactStatus.CONTACTED,
            )
            session.add(c)
            contacts.append(c)
        session.flush()

        # 2 drafts (one per contact)
        for c in contacts:
            session.add(
                Draft(
                    contact_id=c.id,
                    template_id=template.id,
                    template_body_snapshot=template.body,
                    prompt_id=prompt.id,
                    prompt_text_snapshot=prompt.text,
                    subject="s",
                    body="b",
                )
            )

        # 3 sent messages, all against contacts[0]
        for _ in range(3):
            session.add(
                SentMessage(
                    contact_id=contacts[0].id,
                    subject="s",
                    body="b",
                    delivery_status=DeliveryStatus.SENT.value,
                )
            )

        # Todos: 1 open send, 1 scheduled follow-up, 1 done (kept out of open_todos count)
        now = datetime.now(UTC)
        session.add(
            Todo(
                type=TodoType.SEND,
                title="send-open",
                contact_id=contacts[0].id,
                due_at=now,
                status=TodoStatus.OPEN,
            )
        )
        session.add(
            Todo(
                type=TodoType.FOLLOW_UP,
                title="fu-scheduled",
                contact_id=contacts[0].id,
                due_at=now + timedelta(days=5),
                status=TodoStatus.SCHEDULED,
            )
        )
        session.add(
            Todo(
                type=TodoType.SEND,
                title="send-done",
                contact_id=contacts[1].id,
                due_at=now - timedelta(days=1),
                status=TodoStatus.DONE,
                completed_at=now - timedelta(days=1),
            )
        )

        session.commit()
        return org.id


def test_delete_cascades_full_tree(authed: TestClient, session_factory) -> None:
    org_id = _seed_full_tree(session_factory)

    response = authed.delete(f"/api/v1/organisations/{org_id}")
    assert response.status_code == 204

    with session_factory() as session:
        # Organisation gone.
        assert session.get(Organisation, org_id) is None

        # No contacts remain for this org.
        remaining_contacts = session.execute(
            select(func.count())
            .select_from(Contact)
            .where(Contact.organisation_id == org_id)
        ).scalar_one()
        assert remaining_contacts == 0

        # No drafts, sent messages, or todos remain that were tied to those contacts.
        # Because the org tree was the only source of these rows in this test, and each
        # child table has ON DELETE CASCADE on contact_id, the tables must be empty of
        # rows created by _seed_full_tree.
        assert session.execute(select(func.count()).select_from(Draft)).scalar_one() == 0
        assert (
            session.execute(select(func.count()).select_from(SentMessage)).scalar_one() == 0
        )
        assert session.execute(select(func.count()).select_from(Todo)).scalar_one() == 0


def test_delete_empty_organisation_still_returns_204(authed: TestClient) -> None:
    org = authed.post("/api/v1/organisations", json={"name": "Empty"}).json()
    response = authed.delete(f"/api/v1/organisations/{org['id']}")
    assert response.status_code == 204


def test_delete_unknown_org_returns_404(authed: TestClient) -> None:
    response = authed.delete("/api/v1/organisations/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
