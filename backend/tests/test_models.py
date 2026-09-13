import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Activity, Case, Redaction, RedactionType, User


def test_schema_tables_and_constraints(tmp_path) -> None:
    from alembic import command
    from alembic.config import Config

    db = tmp_path / "test.db"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    assert set(inspect(create_engine(f"sqlite:///{db}")).get_table_names()) == {
        "users",
        "cases",
        "activities",
        "redaction_types",
        "redactions",
        "alembic_version",
    }


def test_invalid_values_and_foreign_keys(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'models.db'}")

    @event.listens_for(engine, "connect")
    def enable_fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    from app.database import Base

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Case(case_number="C-1", status="BAD"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(User(first_name="A", last_name="B", email="a@example.com"))
        session.add(RedactionType(name="PII"))
        session.add(Case(case_number="C-2", status="OPEN"))
        session.commit()
        session.add(
            Activity(case_id=1, activity_uid="A-1", activity_type="CALL", description="Synthetic")
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
