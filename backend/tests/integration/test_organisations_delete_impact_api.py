"""GET /api/v1/organisations/{id}/delete-impact — powers the FR-027a confirmation dialog."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType


def test_delete_impact_counts_full_tree(authed: TestClient, session_factory) -> None:
    """Fixture: 3 contacts, drafts on 2 of them, 5 sent_messages, 4 pending todos
    (mix of open + scheduled), 1 done todo that must not count as open."""
    with session_factory() as session:
        template = session.execute(select(Template).limit(1)).scalar_one()
        prompt = session.execute(select(Prompt).limit(1)).scalar_one()

        org = Organisation(name="Impacted")
        session.add(org)
        session.flush()

        contacts: list[Contact] = []
        for i in range(3):
            c = Contact(
                organisation_id=org.id,
                first_name=f"F{i}",
                last_name=f"L{i}",
                email=f"c{i}@impacted.co",
                status=ContactStatus.CONTACTED,
            )
            session.add(c)
            contacts.append(c)
        session.flush()

        # 2 drafts (contacts 0 and 1)
        for c in contacts[:2]:
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

        # 5 sent messages against contacts[0]
        for _ in range(5):
            session.add(
                SentMessage(
                    contact_id=contacts[0].id,
                    subject="s",
                    body="b",
                    delivery_status=DeliveryStatus.SENT.value,
                )
            )

        # 2 open + 2 scheduled = 4 pending todos, plus 1 done that must not count
        now = datetime.now(UTC)
        for i in range(2):
            session.add(
                Todo(
                    type=TodoType.SEND,
                    title=f"open-{i}",
                    contact_id=contacts[0].id,
                    due_at=now,
                    status=TodoStatus.OPEN,
                )
            )
        for i in range(2):
            session.add(
                Todo(
                    type=TodoType.FOLLOW_UP,
                    title=f"sched-{i}",
                    contact_id=contacts[0].id,
                    due_at=now + timedelta(days=5),
                    status=TodoStatus.SCHEDULED,
                )
            )
        session.add(
            Todo(
                type=TodoType.SEND,
                title="done",
                contact_id=contacts[1].id,
                due_at=now - timedelta(days=1),
                status=TodoStatus.DONE,
                completed_at=now - timedelta(days=1),
            )
        )
        session.commit()
        org_id = org.id

    body = authed.get(f"/api/v1/organisations/{org_id}/delete-impact").json()
    assert body["target"] == {"kind": "organisation", "id": org_id, "name": "Impacted"}
    assert body["counts"] == {
        "contacts": 3,
        "drafts": 2,
        "sent_messages": 5,
        "open_todos": 4,
    }


def test_delete_impact_empty_organisation_is_all_zeros(authed: TestClient) -> None:
    org = authed.post("/api/v1/organisations", json={"name": "Empty"}).json()
    body = authed.get(f"/api/v1/organisations/{org['id']}/delete-impact").json()
    assert body["target"]["kind"] == "organisation"
    assert body["target"]["name"] == "Empty"
    assert body["counts"] == {
        "contacts": 0,
        "drafts": 0,
        "sent_messages": 0,
        "open_todos": 0,
    }


def test_delete_impact_unknown_org_returns_404(authed: TestClient) -> None:
    response = authed.get("/api/v1/organisations/999999/delete-impact")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
