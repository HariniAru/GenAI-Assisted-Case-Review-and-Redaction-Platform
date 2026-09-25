import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Activity, Case, Redaction, RedactionType, User


def test_schema_tables_and_constraints(engine) -> None:
    assert set(inspect(engine).get_table_names()) == {
        "users",
        "cases",
        "activities",
        "redaction_types",
        "redactions",
        "alembic_version",
        "reference_chunks",
    }


def test_invalid_values_and_foreign_keys(engine) -> None:
    with Session(engine) as session:
        session.add(Case(case_number="C-1", status="BAD"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(User(first_name="A", last_name="B", email="a@example.com"))
        session.add(RedactionType(name="PII"))
        case = Case(case_number="C-2", status="OPEN")
        session.add(case)
        session.commit()
        session.add(
            Activity(
                case_id=case.id, activity_uid="A-1", activity_type="CALL", description="Synthetic"
            )
        )
        session.commit()
        session.add(
            Redaction(
                activity_id=1,
                redaction_type_id=1,
                user_id=1,
                source="OTHER",
                redaction_text="x",
                starting_position=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            Redaction(
                activity_id=1,
                redaction_type_id=1,
                user_id=1,
                source="AI",
                redaction_text="x",
                starting_position=-1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            Redaction(
                activity_id=999,
                redaction_type_id=1,
                user_id=1,
                source="AI",
                redaction_text="x",
                starting_position=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_migration_round_trip_and_metadata(engine) -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.database import Base
    from tests.conftest import migrate

    migrate(engine, "base", downgrade=True)
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    migrate(engine)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_timestamp_round_trip(engine) -> None:
    from datetime import datetime, timezone

    instant = datetime(2026, 9, 25, 12, 30, tzinfo=timezone.utc)
    with Session(engine) as session:
        item = Case(case_number="TIME-1", status="OPEN", created_at=instant)
        session.add(item)
        session.commit()
        session.refresh(item)
        if engine.dialect.name == "postgresql":
            assert item.created_at.tzinfo is not None
            assert item.created_at == instant
        else:
            assert item.created_at == instant.replace(tzinfo=None)
