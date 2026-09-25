"""Run the same tests on SQLite or an explicitly selected PostgreSQL test database."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url

# Never construct the application engine from a developer's .env during tests.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["DEMO_REVIEWER_EMAIL"] = "jordan.lee@example.com"


def migrate(engine, revision: str = "head", *, downgrade: bool = False) -> None:
    cfg = Config("alembic.ini")
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        operation = command.downgrade if downgrade else command.upgrade
        operation(cfg, revision)


@pytest.fixture
def engine(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        parsed = make_url(url)
        if parsed.drivername != "postgresql+psycopg" or not (parsed.database or "").endswith(
            "_test"
        ):
            pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg and a database ending _test")
        schema = "test_" + uuid4().hex
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine(
            f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
        )

        @event.listens_for(engine, "connect")
        def enable_fk(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    try:
        migrate(engine)
        yield engine
    finally:
        engine.dispose()
        if url:
            with admin.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
            admin.dispose()
