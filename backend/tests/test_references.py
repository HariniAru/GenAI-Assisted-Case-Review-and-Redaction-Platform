import hashlib

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.database import get_db
from app.main import app
from app.models import Activity, Case, Redaction, ReferenceChunk
from app.reference_corpus import CORPUS_PATH, POLICY_HEADINGS, SOURCE, parse_corpus
from app.reference_router import embedding_provider
from app.reference_service import ReferenceRetriever, ingest
from app.seed import seed
from tests.conftest import migrate


class FakeEmbeddings(Embeddings):
    """Deterministic unit/integration vectors; never claimed to measure relevance."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(value) for value in texts]

    def embed_query(self, value: str) -> list[float]:
        values = hashlib.sha256(value.encode()).digest()
        return [float(values[i % 32] + 1) for i in range(384)]


@pytest.fixture
def postgres(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("pgvector integration requires TEST_DATABASE_URL")
    return engine


def test_corpus_boundaries_metadata_and_whole_examples():
    corpus = CORPUS_PATH.read_text()
    docs = parse_corpus(corpus)
    assert len(docs) == 32
    assert {doc.metadata["kind"] for doc in docs} == {
        "policy",
        "glossary",
        "example",
        "summary_guide",
    }
    assert all(doc.metadata["source"] == SOURCE for doc in docs)
    assert all(doc.metadata["status"] in {"seed", "proposed"} for doc in docs)
    assert all(not doc.metadata["section"].startswith("5.") for doc in docs)
    assert not any("## 5." in doc.page_content for doc in docs)
    example = next(d for d in docs if d.metadata.get("activity_uid") == "ACT-1001-01")
    assert example.metadata["status"] == "seed"
    assert "Maria Lopez" in example.page_content and "Customer full name." in example.page_content
    assert (
        "PRIVILEGED" in example.page_content and "Do not label `her father`" in example.page_content
    )
    negative = next(d for d in docs if d.metadata.get("activity_uid") == "ACT-1001-02")
    assert "no redaction suggestions" in negative.page_content
    assert docs == parse_corpus(corpus + "\nEvaluation answer keys stay outside Sections 1–4.")
    with pytest.raises(ValueError):
        parse_corpus(corpus.replace("### PERSONAL_INFO", "### MISSING"))


def test_vector_migration_preserves_case_records(postgres):
    with Session(postgres) as db:
        seed(db)
        db.commit()
    migrate(postgres, "0001_initial_schema", downgrade=True)
    with Session(postgres) as db:
        assert db.scalar(select(func.count(Case.id))) == 5
        assert db.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
    migrate(postgres)
    with Session(postgres) as db:
        assert db.scalar(select(func.count(Redaction.id))) == 6
        assert db.scalar(select(func.count(ReferenceChunk.id))) == 0


def test_ingestion_repeat_update_remove_and_rollback(postgres):
    corpus = CORPUS_PATH.read_text()
    embeddings = FakeEmbeddings()
    with Session(postgres) as db:
        seed(db)
        db.commit()
        first = ingest(db, corpus, embeddings)
        db.commit()
        assert first == {"chunks": 32, "updated": 32, "removed": 0}
        ids = set(db.scalars(select(ReferenceChunk.id)))
        assert ingest(db, corpus, embeddings) == {"chunks": 32, "updated": 0, "removed": 0}
        db.commit()
        changed = corpus.replace("Customer full name.", "Synthetic customer full name.", 1)
        assert ingest(db, changed, embeddings)["updated"] == 1
        db.commit()
        assert set(db.scalars(select(ReferenceChunk.id))) == ids
        reduced = changed.replace(
            changed[changed.index("### ACT-1004-02") : changed.index("### ACT-1005-01")], ""
        )
        assert ingest(db, reduced, embeddings) == {"chunks": 31, "updated": 0, "removed": 1}
        db.commit()

        class Broken(FakeEmbeddings):
            def embed_documents(self, texts):
                return [[float("nan")] * 384 for _ in texts]

        with pytest.raises(ValueError):
            ingest(db, corpus, Broken())
        db.rollback()
        assert db.scalar(select(func.count(ReferenceChunk.id))) == 31
        assert db.scalar(select(func.count(Case.id))) == 5
        assert db.scalar(select(func.count(Redaction.id))) == 6


def test_references_endpoint_read_only_metadata_and_errors(postgres):
    sessions = sessionmaker(bind=postgres)
    embeddings = FakeEmbeddings()
    with sessions.begin() as db:
        seed(db)
        aid = db.scalar(select(Activity.id).where(Activity.activity_uid == "ACT-1005-01"))

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[embedding_provider] = lambda: embeddings
    try:
        with TestClient(app) as client:
            assert client.get("/activities/999999/references").status_code == 404
            assert client.get(f"/activities/{aid}/references").status_code == 503
            with sessions.begin() as db:
                ingest(db, CORPUS_PATH.read_text(), embeddings)
            response = client.get(f"/activities/{aid}/references")
            assert response.status_code == 200
            docs = response.json()
            policies = [d for d in docs if d["metadata"]["kind"] == "policy"]
            assert {d["metadata"]["section"][3:] for d in policies} == POLICY_HEADINGS
            examples = [d for d in docs if d["metadata"]["kind"] == "example"]
            assert len(examples) == 3
            assert all(d["metadata"]["activity_uid"].startswith("ACT-") for d in examples)
            terms = {d["metadata"]["term"] for d in docs if d["metadata"]["kind"] == "glossary"}
            assert {"cust", "c/b", "acct", "clld"} <= terms
            assert "re" not in terms  # Does not match inside "requested".
            with sessions() as db:
                assert db.scalar(select(func.count(ReferenceChunk.id))) == 32
                assert db.scalar(select(func.count(Redaction.id))) == 6
                retriever = ReferenceRetriever(session=db, embeddings=embeddings)
                short = retriever.invoke("custard regarding")
                assert not any(d.metadata["kind"] == "glossary" for d in short)
            with sessions.begin() as db:
                db.execute(update(ReferenceChunk).values(model_key="different-model"))
            assert client.get(f"/activities/{aid}/references").status_code == 503
            with sessions.begin() as db:
                assert ingest(db, CORPUS_PATH.read_text(), embeddings)["updated"] == 32
            with sessions.begin() as db:
                db.execute(
                    delete(ReferenceChunk).where(
                        ReferenceChunk.chunk_metadata["section"].as_string() == "1. PRIVILEGED"
                    )
                )
            assert client.get(f"/activities/{aid}/references").status_code == 503
    finally:
        app.dependency_overrides.clear()
