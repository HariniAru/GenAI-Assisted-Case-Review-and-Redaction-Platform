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
# Tests must never send fixture text or consume a developer's tracing credentials.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""


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
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema},public"})
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


@pytest.fixture
def grounded_retriever(engine):
    """Index corpus policy rows locally, but fake retrieval for generation tests."""
    from sqlalchemy.orm import Session

    from app.ai_router import recommendation_retriever
    from app.main import app
    from app.models import ReferenceChunk
    from app.reference_corpus import CORPUS_PATH, SOURCE, parse_corpus
    from app.reference_embeddings import model_key

    documents = parse_corpus(CORPUS_PATH.read_text())
    with Session(engine) as db:
        for doc in documents:
            db.add(
                ReferenceChunk(
                    id=doc.id,
                    source=SOURCE,
                    content=doc.page_content,
                    chunk_metadata=doc.metadata,
                    model_key=model_key(),
                    embedding=[1.0] * 384,
                )
            )
        db.commit()

    class FakeRetriever:
        def __init__(self):
            self.documents = documents
            self.queries = []
            self.error = None

        def invoke(self, description):
            self.queries.append(description)
            if self.error:
                raise self.error
            return self.documents

    retriever = FakeRetriever()
    app.dependency_overrides[recommendation_retriever] = lambda: retriever
    try:
        yield retriever
    finally:
        app.dependency_overrides.pop(recommendation_retriever, None)
