from __future__ import annotations

import sys
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Activity, Case, Redaction, RedactionType, User


@dataclass(frozen=True)
class ActivitySeed:
    uid: str
    case_number: str
    activity_type: str
    description: str


ACTIVITIES = (
    ActivitySeed(
        "ACT-1001-01",
        "CASE-1001",
        "Call - Inbound",
        "Spoke with cust Maria Lopez re cust concerns. Cust called from (555) 014-7821 re acct 884129. Cust sts her father had the veh in drive and the veh accelerated unexpectedly before striking a garage wall. Internal recs indicate maximum settlement authorization is $4,000. Co counsel adv team not to admit liability until investigation is complete. Cust sks c/b from case mgr.",
    ),
    ActivitySeed(
        "ACT-1001-02",
        "CASE-1001",
        "Internal Note",
        "Outbound c/b to cust. Adv cust to submit repair docs and written req to Northstar Claims Dept. Cust thanked and requires no further asst.",
    ),
    ActivitySeed(
        "ACT-1002-01",
        "CASE-1002",
        "Call - Outbound",
        "Clld cust Daniel Kim at (555) 011-2234 re acct 771205. Unable to reach cust. LM requesting c/b re veh inspection.",
    ),
    ActivitySeed(
        "ACT-1002-02",
        "CASE-1002",
        "Internal Note",
        "Reviewed internal pricing recs. Possible goodwill reimbursement limit is $1,500 pending mgr review. Do not disclose internal limit to cust.",
    ),
    ActivitySeed(
        "ACT-1003-01",
        "CASE-1003",
        "Close",
        "5 Point Close. Summary: Cust sts veh stalled after service. Action Taken: Adv cust inspection completed. Resolution: Cust notified of final decision. Cust satisfied: yes. No further asst.",
    ),
    ActivitySeed(
        "ACT-1004-01",
        "CASE-1004",
        "Call - Inbound",
        "Cust Priya Shah called from (555) 016-4402 re acct 998231. Cust reports veh stalled near home after service. Internal review notes provisional reimbursement cap of $2,200. Counsel advises preserve inspection photos. Safety concern: brake pedal felt soft.",
    ),
    ActivitySeed(
        "ACT-1004-02",
        "CASE-1004",
        "Internal Note",
        "Mgr approved goodwill review. Do not disclose internal pricing guidance to cust until final decision.",
    ),
    ActivitySeed(
        "ACT-1005-01",
        "CASE-1005",
        "Call - Outbound",
        "Clld cust Omar Reed at (555) 019-8820. Cust confirmed mailing address 42 Pinecrest Way and requested a c/b about acct 443210. No legal advice discussed.",
    ),
)

REDACTIONS = (
    ("Maria Lopez", "PERSONAL_INFO", "AI"),
    ("(555) 014-7821", "PERSONAL_INFO", "MANUAL"),
    ("884129", "PERSONAL_INFO", "AI"),
    ("maximum settlement authorization is $4,000", "CONFIDENTIAL", "MANUAL"),
    (
        "Co counsel adv team not to admit liability until investigation is complete.",
        "PRIVILEGED",
        "AI",
    ),
    ("veh accelerated unexpectedly", "HIGHLIGHT", "MANUAL"),
)


def _one(session: Session, model, **filters):
    return session.scalar(select(model).filter_by(**filters))


def seed(session: Session) -> dict[str, int]:
    user = _one(session, User, email="jordan.lee@example.com")
    if user is None:
        user = User(first_name="Jordan", last_name="Lee", email="jordan.lee@example.com")
        session.add(user)
        session.flush()

    types = {}
    for name in ("PERSONAL_INFO", "CONFIDENTIAL", "PRIVILEGED", "HIGHLIGHT"):
        item = _one(session, RedactionType, name=name)
        if item is None:
            item = RedactionType(name=name, deleted_at=None)
            session.add(item)
            session.flush()
        types[name] = item

    cases = {}
    for number, status in (
        ("CASE-1001", "OPEN"),
        ("CASE-1002", "IN_PROGRESS"),
        ("CASE-1003", "CLOSED"),
        ("CASE-1004", "OPEN"),
        ("CASE-1005", "OPEN"),
    ):
        item = _one(session, Case, case_number=number)
        if item is None:
            item = Case(case_number=number, status=status, ai_summary=None)
            session.add(item)
            session.flush()
        elif number == "CASE-1001":
            item.status = "IN_PROGRESS"
        elif number == "CASE-1002":
            item.status = "OPEN"
        cases[number] = item

    activities = {}
    for data in ACTIVITIES:
        item = _one(session, Activity, activity_uid=data.uid)
        if item is None:
            item = Activity(
                case=cases[data.case_number],
                activity_uid=data.uid,
                activity_type=data.activity_type,
                description=data.description,
            )
            session.add(item)
            session.flush()
        activities[data.uid] = item

    for text, type_name, source in REDACTIONS:
        activity = activities["ACT-1001-01"]
        starts = [
            i for i in range(len(activity.description)) if activity.description.startswith(text, i)
        ]
        if len(starts) != 1:
            raise ValueError(f"Seed redaction target must occur exactly once: {text!r}")
        start = starts[0]
        end = start + len(text)
        if activity.description[start:end] != text:
            raise ValueError(f"Seed redaction slice mismatch: {text!r}")
        existing = session.scalar(
            select(Redaction).filter_by(
                activity=activity,
                redaction_type=types[type_name],
                user=user,
                source=source,
                redaction_text=text,
                starting_position=start,
            )
        )
        if existing is None:
            session.add(
                Redaction(
                    activity=activity,
                    redaction_type=types[type_name],
                    user=user,
                    source=source,
                    redaction_text=text,
                    starting_position=start,
                )
            )

    session.flush()
    return {
        name: session.scalar(select(func.count(model.id))) or 0
        for name, model in (
            ("users", User),
            ("redaction_types", RedactionType),
            ("cases", Case),
            ("activities", Activity),
            ("redactions", Redaction),
        )
    }


def main() -> int:
    try:
        with SessionLocal.begin() as session:
            counts = seed(session)
        print(" ".join(f"{name}: {count}" for name, count in counts.items()))
        return 0
    except (SQLAlchemyError, ValueError) as exc:
        print(f"Seeding failed; transaction rolled back: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
