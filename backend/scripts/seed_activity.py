"""Seed synthetic activity_event rows for load testing (T045).

Used by the SC-012 performance target (50k events / 5k contacts, first-page render < 2 s)
and by quickstart § 4. Distribution mirrors what a working operator generates over a year:
lots of `email_sent` / `todo_completed`, some `enrichment_attempted` / `draft_generated`,
few status changes and mailbox stores.

Usage:
    uv run python scripts/seed_activity.py --events 50000 --contacts 5000
"""
from __future__ import annotations

import argparse
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.activity_event import ActivityActor, ActivityEvent, ActivityEventType
from app.models.contact import Contact, ContactStatus
from app.models.organisation import Organisation


_DISTRIBUTION: list[tuple[ActivityEventType, int]] = [
    (ActivityEventType.EMAIL_SENT, 20),
    (ActivityEventType.TODO_COMPLETED, 18),
    (ActivityEventType.TODO_CREATED, 15),
    (ActivityEventType.ENRICHMENT_ATTEMPTED, 12),
    (ActivityEventType.DRAFT_GENERATED, 10),
    (ActivityEventType.FOLLOW_UP_SCHEDULED, 8),
    (ActivityEventType.STATUS_CHANGED, 6),
    (ActivityEventType.DRAFT_STORED_IN_MAILBOX, 4),
    (ActivityEventType.LEAD_CREATED, 4),
    (ActivityEventType.SEND_FAILED, 2),
    (ActivityEventType.MAILBOX_STORE_FAILED, 1),
]


def _weighted_types(rng: random.Random, n: int) -> list[ActivityEventType]:
    pool: list[ActivityEventType] = []
    for et, weight in _DISTRIBUTION:
        pool.extend([et] * weight)
    return [rng.choice(pool) for _ in range(n)]


def seed(session: Session, *, contacts: int, events: int, seed_value: int) -> None:
    rng = random.Random(seed_value)

    org = Organisation(name=f"SeedCo-{seed_value}", domain=f"seed{seed_value}.example")
    session.add(org)
    session.flush()

    contact_rows: list[Contact] = []
    for i in range(contacts):
        contact_rows.append(
            Contact(
                organisation_id=org.id,
                first_name="Seed",
                last_name=f"Contact-{i}",
                email=f"seed-{i}@seed{seed_value}.example",
                status=ContactStatus.NEW,
            )
        )
        if len(contact_rows) >= 500:
            session.add_all(contact_rows)
            session.flush()
            contact_rows = []
    if contact_rows:
        session.add_all(contact_rows)
        session.flush()

    contact_ids = [c.id for c in session.query(Contact).filter_by(organisation_id=org.id).all()]
    types = _weighted_types(rng, events)
    base_ts = datetime.now(UTC) - timedelta(days=365)

    batch: list[ActivityEvent] = []
    for i, et in enumerate(types):
        cid = rng.choice(contact_ids)
        batch.append(
            ActivityEvent(
                contact_id=cid,
                organisation_id=org.id,
                event_type=et,
                actor=ActivityActor.OPERATOR if rng.random() > 0.2 else ActivityActor.SYSTEM,
                payload={},
                occurred_at=base_ts + timedelta(seconds=i * 60),
            )
        )
        if len(batch) >= 5_000:
            session.add_all(batch)
            session.flush()
            batch = []
    if batch:
        session.add_all(batch)
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic activity events for load testing.")
    parser.add_argument("--events", type=int, default=50_000)
    parser.add_argument("--contacts", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=1, help="RNG seed for reproducible data")
    args = parser.parse_args()

    with SessionLocal() as session:
        seed(session, contacts=args.contacts, events=args.events, seed_value=args.seed)

    print(f"Inserted {args.events:,} events across {args.contacts:,} contacts.")


if __name__ == "__main__":
    main()
