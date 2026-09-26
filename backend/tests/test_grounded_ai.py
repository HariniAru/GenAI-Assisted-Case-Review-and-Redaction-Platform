import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import ai_router, ai_service
from app.ai_grounding import MAX_CONTEXT_CHARS, MAX_DESCRIPTION_CHARS, build_grounding
from app.database import get_db
from app.main import app
from app.models import Activity, Case, Redaction, ReferenceChunk
from app.reference_corpus import CORPUS_PATH, chunk_id, parse_corpus
from app.reference_service import IndexUnavailable
from app.schemas import AIRecommendation, AIRecommendationResponse
from app.seed import seed


@pytest.fixture
def grounded_api(engine, grounded_retriever, monkeypatch):
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        seed(db)
        activity = db.scalar(select(Activity).where(Activity.activity_uid == "ACT-1005-01"))
        aid, cid, description = activity.id, activity.case_id, activity.description

    class Model:
        def __init__(self):
            self.calls = []
            self.recommendations = [
                AIRecommendation(
                    redaction_type="PERSONAL_INFO",
                    redaction_text="Omar Reed",
                    starting_position=description.index("Omar Reed"),
                    reason="Customer full name",
                )
            ]
            self.error = None

        def recommend(self, description, types, context):
            self.calls.append((description, types, context))
            if self.error:
                raise self.error
            return AIRecommendationResponse(recommendations=self.recommendations)

    model = Model()
    monkeypatch.setattr(ai_router, "provider", model)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                sessions=sessions,
                model=model,
                retriever=grounded_retriever,
                aid=aid,
                cid=cid,
                description=description,
                generate=f"/activities/{aid}/ai-recommendations",
                accept=f"/activities/{aid}/ai-recommendations/accept",
            )
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_grounded_context_evidence_and_explicit_acceptance(grounded_api):
    api = grounded_api
    response = api.client.post(api.generate)
    assert response.status_code == 200
    rec = response.json()["recommendations"][0]
    assert api.retriever.queries == [api.description]
    description, types, context = api.model.calls[0]
    assert description == api.description and "PERSONAL_INFO" in types
    assert "Protect a customer's full name" in context
    assert "2. c/b" in context
    assert "ACT-1005-01" not in context
    assert "ACT-1001-01" in context
    assert len(context) <= MAX_CONTEXT_CHARS
    evidence = rec["supporting_policy"]
    assert evidence["chunk_id"] == chunk_id("1. PERSONAL_INFO")
    assert evidence["section"] == "1. PERSONAL_INFO"
    with api.sessions() as db:
        row = db.get(ReferenceChunk, evidence["chunk_id"])
        assert row.chunk_metadata["kind"] == "policy"
        assert evidence["excerpt"].rstrip("…") in row.content
        assert db.scalar(select(func.count(Redaction.id))) == 6
    # Reason is not authority and is not persisted.
    accepted = api.client.post(api.accept, json={**rec, "reason": "Untrusted client rationale"})
    assert accepted.status_code == 201
    assert accepted.json()["source"] == "AI"
    assert "reason" not in accepted.json() and "supporting_policy" not in accepted.json()
    assert api.client.post(api.accept, json=rec).status_code == 409
    assert api.client.post(api.generate).json()["recommendations"] == []
    with api.sessions() as db:
        assert db.scalar(select(func.count(Redaction.id))) == 7
        assert db.get(Activity, api.aid).description == api.description


def test_filters_invalid_types_text_ambiguous_offsets_and_duplicates(grounded_api):
    api = grounded_api
    good = api.model.recommendations[0]
    api.model.recommendations = [
        good,
        good,
        good.model_copy(update={"redaction_type": "UNSUPPORTED"}),
        good.model_copy(update={"redaction_text": "invented name"}),
        good.model_copy(update={"redaction_text": " "}),
        good.model_copy(update={"redaction_text": "cust", "starting_position": 99999}),
    ]
    # Make the offset ambiguous so the existing unique-match correction cannot fix it.
    with api.sessions.begin() as db:
        db.get(Activity, api.aid).description = "cust " + api.description + " cust"
    body = api.client.post(api.generate).json()["recommendations"]
    assert len(body) == 1
    assert body[0]["redaction_text"] == "Omar Reed"
    assert body[0]["starting_position"] == api.description.index("Omar Reed") + 5
    with api.sessions() as db:
        assert db.scalar(select(func.count(Redaction.id))) == 6


@pytest.mark.parametrize(
    "change", ["offset", "text", "type", "chunk", "section", "excerpt", "extra"]
)
def test_acceptance_rejects_tampered_payload(grounded_api, change):
    api = grounded_api
    rec = api.client.post(api.generate).json()["recommendations"][0]
    if change == "offset":
        rec["starting_position"] = -1
    elif change == "text":
        rec["redaction_text"] = "invented text"
    elif change == "type":
        rec["redaction_type"] = "HIGHLIGHT"  # Valid label, wrong supporting policy.
    elif change == "chunk":
        rec["supporting_policy"]["chunk_id"] = "invented"
    elif change == "section":
        rec["supporting_policy"]["section"] = "3. Example"
    elif change == "excerpt":
        rec["supporting_policy"]["excerpt"] = "Fabricated policy"
    else:
        rec["user_id"] = 999
    assert api.client.post(api.accept, json=rec).status_code == 422
    with api.sessions() as db:
        assert db.scalar(select(func.count(Redaction.id))) == 6


def test_acceptance_rechecks_current_description_and_policy(grounded_api):
    api = grounded_api
    rec = api.client.post(api.generate).json()["recommendations"][0]
    with api.sessions.begin() as db:
        db.get(Activity, api.aid).description = "Changed synthetic description."
    assert api.client.post(api.accept, json=rec).status_code == 422
    with api.sessions.begin() as db:
        db.get(Activity, api.aid).description = api.description
        db.get(ReferenceChunk, rec["supporting_policy"]["chunk_id"]).content += " Updated policy."
    assert api.client.post(api.accept, json=rec).status_code == 422


def test_retrieval_failure_empty_output_closed_and_unknown(grounded_api):
    api = grounded_api
    assert api.client.post("/activities/999999/ai-recommendations").status_code == 404
    api.retriever.error = IndexUnavailable("Private internal connection details")
    response = api.client.post(api.generate)
    assert response.status_code == 503
    assert "Reference retrieval" in response.json()["detail"]
    assert "Private" not in response.text
    assert api.model.calls == []
    api.retriever.error = None
    api.retriever.documents = [d for d in api.retriever.documents if d.metadata["kind"] != "policy"]
    assert api.client.post(api.generate).status_code == 503
    assert api.model.calls == []
    api.retriever.documents = parse_corpus(CORPUS_PATH.read_text())
    api.model.recommendations = []
    assert api.client.post(api.generate).json() == {"recommendations": []}
    api.model.error = RuntimeError("Private provider details")
    response = api.client.post(api.generate)
    assert response.status_code == 502 and "Private" not in response.text
    with api.sessions.begin() as db:
        db.get(Case, api.cid).status = "CLOSED"
    calls = len(api.model.calls)
    assert api.client.post(api.generate).status_code == 409
    assert len(api.model.calls) == calls


def test_closed_case_acceptance_and_bounded_input(grounded_api):
    api = grounded_api
    rec = api.client.post(api.generate).json()["recommendations"][0]
    with api.sessions.begin() as db:
        db.get(Case, api.cid).status = "CLOSED"
    assert api.client.post(api.accept, json=rec).status_code == 409
    with api.sessions.begin() as db:
        db.get(Case, api.cid).status = "OPEN"
        db.get(Activity, api.aid).description = "x" * (MAX_DESCRIPTION_CHARS + 1)
    calls = len(api.model.calls)
    assert api.client.post(api.generate).status_code == 422
    assert len(api.model.calls) == calls


def test_prompt_bounds_never_truncate_mandatory_policy():
    docs = parse_corpus(CORPUS_PATH.read_text())
    for doc in docs:
        if doc.metadata["kind"] == "example":
            doc.page_content *= 100
    context = build_grounding(docs, "ACT-1005-01")
    assert len(context.text) <= MAX_CONTEXT_CHARS
    assert "Protect a customer's full name" in context.text
    assert '"kind": "example"' not in context.text
    docs[0].page_content = "x" * (MAX_CONTEXT_CHARS + 1)
    with pytest.raises(IndexUnavailable):
        build_grounding(docs, "ACT-1005-01")


def test_provider_uses_grounding_and_rejects_model_invented_evidence(monkeypatch):
    requests = []
    output = {"recommendations": []}

    class Client:
        def __init__(self, **kwargs):
            pass

        def chat_completion(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(output)))]
            )

    monkeypatch.setattr(ai_service, "InferenceClient", Client)
    monkeypatch.setattr(
        ai_service,
        "get_settings",
        lambda: SimpleNamespace(
            hf_token="fake-test-token", hf_provider="nscale", hf_model="Qwen/Qwen3-32B"
        ),
    )
    provider = ai_service.HuggingFaceRecommendationProvider()
    provider.recommend("Current synthetic note", ["PERSONAL_INFO"], "POLICY CONTEXT")
    request = requests[0]
    assert request["messages"][1]["content"] == "Current synthetic note"
    assert "POLICY CONTEXT" in request["messages"][0]["content"]
    assert "take precedence" in request["messages"][0]["content"]
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["max_tokens"] == 2048
    output["recommendations"] = [
        {
            "redaction_type": "PERSONAL_INFO",
            "redaction_text": "note",
            "starting_position": 18,
            "reason": "Name",
            "supporting_policy": {"chunk_id": "invented"},
        }
    ]
    with pytest.raises(ValidationError):
        provider.recommend("Current synthetic note", ["PERSONAL_INFO"], "POLICY CONTEXT")


def test_generation_uses_existing_pgvector_index(engine, monkeypatch):
    """Real retriever + SQL index, fake embeddings/model, isolated database only."""
    if engine.dialect.name != "postgresql":
        pytest.skip("pgvector integration requires TEST_DATABASE_URL")
    from app.reference_router import embedding_provider
    from app.reference_service import ingest
    from tests.test_references import FakeEmbeddings

    sessions = sessionmaker(bind=engine)
    embeddings = FakeEmbeddings()
    with sessions.begin() as db:
        seed(db)
        ingest(db, CORPUS_PATH.read_text(), embeddings)
        aid = db.scalar(select(Activity.id).where(Activity.activity_uid == "ACT-1005-01"))

    class Model:
        def recommend(self, description, types, context):
            assert "Protect a customer's full name" in context
            assert "3. ACT-1005-01" not in context
            assert '"kind": "example"' in context
            return AIRecommendationResponse(
                recommendations=[
                    AIRecommendation(
                        redaction_type="PERSONAL_INFO",
                        redaction_text="Omar Reed",
                        starting_position=description.index("Omar Reed"),
                        reason="Customer name",
                    )
                ]
            )

    monkeypatch.setattr(ai_router, "provider", Model())

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[embedding_provider] = lambda: embeddings
    try:
        with TestClient(app) as client:
            response = client.post(f"/activities/{aid}/ai-recommendations")
            assert response.status_code == 200
            assert (
                response.json()["recommendations"][0]["supporting_policy"]["section"]
                == "1. PERSONAL_INFO"
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(embedding_provider, None)
