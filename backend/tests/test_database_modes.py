from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app import ai_router
from app.analysis_router import analysis_graph
from app.case_analysis import build_analysis_graph
from app.database import get_db
from app.main import app
from app.models import Case, Redaction
from app.reference_router import embedding_provider
from app.reference_service import ReferenceRetriever
from app.seed import seed


def test_unavailable_retrieval_never_falls_back_to_models(engine, monkeypatch):
    """Real retriever: SQLite unsupported, or PostgreSQL index not ingested."""
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        seed(db)

    class NoEmbeddings(Embeddings):
        def embed_documents(self, texts):
            raise AssertionError("Unavailable retrieval must not load an embedding model")

        def embed_query(self, text):
            raise AssertionError("Unavailable retrieval must not embed case text")

    class NoProvider:
        def recommend(self, *args):
            raise AssertionError("Unavailable retrieval must not call the model")

        def summarize(self, *args):
            raise AssertionError("Unavailable guidance must not call the model")

    embeddings = NoEmbeddings()
    provider = NoProvider()
    monkeypatch.setattr(ai_router, "provider", provider)
    graph = build_analysis_graph(
        sessions, provider, lambda db: ReferenceRetriever(session=db, embeddings=embeddings)
    )

    def override_db():
        with sessions() as db:
            yield db

    def snapshot():
        with sessions() as db:
            return (
                list(db.execute(select(Case.__table__).order_by(Case.id))),
                list(db.execute(select(Redaction.__table__).order_by(Redaction.id))),
            )

    before = snapshot()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[embedding_provider] = lambda: embeddings
    app.dependency_overrides[analysis_graph] = lambda: graph
    try:
        with TestClient(app) as client:
            assert client.get("/cases/2").status_code == 200
            references = client.get("/activities/3/references")
            assert references.status_code == 503
            if engine.dialect.name == "sqlite":
                assert "requires PostgreSQL" in references.json()["detail"]
            assert client.post("/activities/3/ai-recommendations").status_code == 503
            assert client.post("/cases/2/analyze").status_code == 503
        assert snapshot() == before
    finally:
        app.dependency_overrides.clear()
