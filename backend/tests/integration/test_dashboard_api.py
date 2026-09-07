"""GET /api/v1/dashboard/overview — aggregation correctness + onboarding shape."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models.contact import Contact, ContactStatus
from app.models.draft import Draft
from app.models.organisation import Organisation
from app.models.prompt import Prompt
from app.models.sent_message import DeliveryStatus, SentMessage
from app.models.template import Template
from app.models.todo import Todo, TodoStatus, TodoType


def test_onboarding_shape_when_no_contacts(authed: TestClient) -> None:
    response = authed.get("/api/v1/dashboard/overview")
    assert response.status_code == 200
    body = response.json()
    assert body == {"onboarding_required": True}


def _seed_baseline(session_factory) -> None:
    """Build a known fixture:
    - 3 contacts created today (leads_added_7d = 3)
    - 2 drafts generated today (drafts_generated_7d = 2)
    - 4 sent emails today (emails_sent_7d = 4)
    - 1 sent email 8 days ago (in prior 7d window, not in current 7d)
    - 1 REPLIED contact updated today (replies_logged_7d = 1)
    - 1 MEETING_BOOKED contact updated today (funnel_30d.meeting_booked = 1)
    - 2 follow_up todos that came due 2 days ago (backward-looking follow_ups_due 7d = 2)
    - 1 open send todo overdue (overdue_count = 1)
    - 1 open send todo due today (due_today_count = 1)
    - 1 follow-up scheduled 3 days in the future (does NOT count in backward window)
    """
    with session_factory() as session:
        now = datetime.now(UTC)
        template = session.execute(
            __import__("sqlalchemy").select(Template).limit(1)
        ).scalar_one()
        prompt = session.execute(
            __import__("sqlalchemy").select(Prompt).limit(1)
        ).scalar_one()

        org = Organisation(name="Acme")
        session.add(org)
        session.flush()

        contacts: list[Contact] = []
        for i in range(3):
            c = Contact(
                organisation_id=org.id,
                first_name=f"F{i}",
                last_name=f"L{i}",
                email=f"c{i}@acme.com",
                status=ContactStatus.ENRICHED,
            )
            session.add(c)
            contacts.append(c)
        session.flush()

        # 2 drafts today
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

        # 4 sent emails today
        for _ in range(4):
            session.add(
                SentMessage(
                    contact_id=contacts[0].id,
                    subject="s",
                    body="b",
                    delivery_status=DeliveryStatus.SENT.value,
                )
            )

        # 1 sent 8 days ago — outside current 7d, inside prior 7d.
        old_sent = SentMessage(
            contact_id=contacts[0].id,
            subject="old",
            body="b",
            delivery_status=DeliveryStatus.SENT.value,
        )
        session.add(old_sent)
        session.flush()
        old_sent.sent_at = now - timedelta(days=8)

        # 1 REPLIED contact, updated today — funnel replied + activity replies_logged.
        contacts[1].status = ContactStatus.REPLIED
        # 1 MEETING_BOOKED contact, updated today.
        contacts[2].status = ContactStatus.MEETING_BOOKED

        # Todos:
        # - 1 overdue open send
        session.add(
            Todo(
                type=TodoType.SEND,
                title="overdue",
                contact_id=contacts[0].id,
                due_at=now - timedelta(hours=1),
                status=TodoStatus.OPEN,
            )
        )
        # - 1 open send due later today
        session.add(
            Todo(
                type=TodoType.SEND,
                title="today",
                contact_id=contacts[0].id,
                due_at=now.replace(hour=23, minute=0, second=0, microsecond=0),
                status=TodoStatus.OPEN,
            )
        )
        # - 2 follow_up todos that became due 2 days ago (backward window)
        for i in range(2):
            session.add(
                Todo(
                    type=TodoType.FOLLOW_UP,
                    title=f"fu{i}",
                    contact_id=contacts[0].id,
                    due_at=now - timedelta(days=2),
                    status=TodoStatus.OPEN,
                )
            )
        # - 1 follow-up 3 days in the future — outside the backward-looking window.
        session.add(
            Todo(
                type=TodoType.FOLLOW_UP,
                title="fu-later",
                contact_id=contacts[0].id,
                due_at=now + timedelta(days=3),
                status=TodoStatus.SCHEDULED,
            )
        )

        session.commit()


def test_full_body_has_expected_counts(authed: TestClient, session_factory) -> None:
    _seed_baseline(session_factory)
    body = authed.get("/api/v1/dashboard/overview").json()
    assert body["onboarding_required"] is False

    todos = body["todos"]
    # 1 send todo overdue by 1h + 2 follow_ups overdue by 2 days = 3.
    assert todos["overdue_count"] == 3
    assert todos["due_today_count"] >= 1  # at least the "today" send todo
    assert todos["next_action"] is not None
    # The 2-day-old follow-ups are the oldest → one of them wins the "next action" slot.
    assert todos["next_action"]["title"].startswith("fu")

    activity = body["activity"]
    assert activity["window_days"] == 7
    assert activity["leads_added"] == 3
    assert activity["drafts_generated"] == 2
    assert activity["emails_sent"] == 4
    assert activity["follow_ups_due"] == 2  # 2 that came due 2d ago; future one excluded
    assert activity["replies_logged"] == 1

    delta = activity["delta_vs_prior"]
    # Prior 7d contains only the old sent email (1). Current 7d has 4. Delta: +3.
    assert delta["emails_sent"] == 3
    # No leads/drafts/replies/follow-ups in prior window.
    assert delta["leads_added"] == 3
    assert delta["drafts_generated"] == 2
    assert delta["replies_logged"] == 1

    activity_30 = body["activity_30d"]
    assert activity_30["window_days"] == 30
    # 30d window covers the old sent (8 days ago) too — 5 sent in total.
    assert activity_30["emails_sent"] == 5

    funnel = body["funnel_30d"]
    assert funnel["sent"] == 5
    assert funnel["replied"] == 1
    assert funnel["meeting_booked"] == 1
    # rate = replied / sent
    assert abs(funnel["reply_rate"] - 1 / 5) < 1e-6
    assert abs(funnel["booking_rate"] - 1 / 5) < 1e-6


def test_dashboard_metrics_match_direct_sql(
    authed: TestClient, session_factory
) -> None:
    """SC-010: every headline number must equal the value of a direct query over the same
    window. If this diverges, the dashboard is misleading and must be fixed."""
    from sqlalchemy import func, select

    _seed_baseline(session_factory)
    body = authed.get("/api/v1/dashboard/overview").json()

    with session_factory() as session:
        now = datetime.now(UTC)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        overdue_sql = session.execute(
            select(func.count())
            .select_from(Todo)
            .where(
                Todo.status.in_([TodoStatus.SCHEDULED, TodoStatus.OPEN]),
                Todo.due_at < now,
            )
        ).scalar_one()
        assert body["todos"]["overdue_count"] == overdue_sql

        leads_7 = session.execute(
            select(func.count())
            .select_from(Contact)
            .where(Contact.created_at >= seven_days_ago, Contact.created_at < now)
        ).scalar_one()
        assert body["activity"]["leads_added"] == leads_7

        sent_7 = session.execute(
            select(func.count())
            .select_from(SentMessage)
            .where(
                SentMessage.sent_at >= seven_days_ago,
                SentMessage.sent_at < now,
                SentMessage.delivery_status == DeliveryStatus.SENT.value,
            )
        ).scalar_one()
        assert body["activity"]["emails_sent"] == sent_7

        sent_30 = session.execute(
            select(func.count())
            .select_from(SentMessage)
            .where(
                SentMessage.sent_at >= thirty_days_ago,
                SentMessage.sent_at < now,
                SentMessage.delivery_status == DeliveryStatus.SENT.value,
            )
        ).scalar_one()
        assert body["funnel_30d"]["sent"] == sent_30

        replied_30 = session.execute(
            select(func.count())
            .select_from(Contact)
            .where(
                Contact.status == ContactStatus.REPLIED,
                Contact.updated_at >= thirty_days_ago,
                Contact.updated_at < now,
            )
        ).scalar_one()
        assert body["funnel_30d"]["replied"] == replied_30


def test_promotes_scheduled_before_counting(
    authed: TestClient, session_factory
) -> None:
    """A scheduled todo whose due_at is in the past should count as overdue after
    the dashboard call runs (promotion is part of GET /dashboard/overview)."""
    with session_factory() as session:
        org = Organisation(name="X")
        session.add(org)
        session.flush()
        contact = Contact(
            organisation_id=org.id,
            first_name="A",
            last_name="B",
            status=ContactStatus.ENRICHED,
        )
        session.add(contact)
        session.flush()
        session.add(
            Todo(
                type=TodoType.FOLLOW_UP,
                title="was-scheduled",
                contact_id=contact.id,
                due_at=datetime.now(UTC) - timedelta(hours=2),
                status=TodoStatus.SCHEDULED,
            )
        )
        session.commit()

    body = authed.get("/api/v1/dashboard/overview").json()
    assert body["todos"]["overdue_count"] >= 1

    with session_factory() as session:
        promoted = session.execute(
            __import__("sqlalchemy")
            .select(Todo)
            .where(Todo.title == "was-scheduled")
        ).scalar_one()
        assert promoted.status == TodoStatus.OPEN
