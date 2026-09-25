from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, Case, Redaction, RedactionType
from app.seed import ACTIVITIES, seed


def test_seed_is_deterministic_and_consistent(engine) -> None:
    with Session(engine) as session:
        first = seed(session)
        session.commit()
        second = seed(session)
        session.commit()
        assert (
            first
            == second
            == {"users": 1, "redaction_types": 4, "cases": 5, "activities": 8, "redactions": 6}
        )
        assert {c.status for c in session.scalars(select(Case))} == {
            "OPEN",
            "IN_PROGRESS",
            "CLOSED",
        }
        assert {t.name for t in session.scalars(select(RedactionType))} == {
            "PERSONAL_INFO",
            "CONFIDENTIAL",
            "PRIVILEGED",
            "HIGHLIGHT",
        }
        assert {r.source for r in session.scalars(select(Redaction))} == {"AI", "MANUAL"}
        assert {a.description for a in session.scalars(select(Activity))} == {
            a.description for a in ACTIVITIES
        }
        expected_cases = {a.uid: a.case_number for a in ACTIVITIES}
        for activity in session.scalars(select(Activity)):
            assert activity.case.case_number == expected_cases[activity.activity_uid]
            for redaction in activity.redactions:
                end = redaction.starting_position + len(redaction.redaction_text)
                assert (
                    activity.description[redaction.starting_position : end]
                    == redaction.redaction_text
                )
                assert redaction.user.email == "jordan.lee@example.com"
