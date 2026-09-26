import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai_grounding import LABELS
from app.analysis_router import analysis_graph
from app.case_analysis import build_analysis_graph
from app.database import get_db
from app.main import app
from app.models import Activity, Case, Redaction, ReferenceChunk
from app.reference_corpus import chunk_id
from app.schemas import AIRecommendation, AIRecommendationResponse, AISummaryResponse
from app.seed import seed


@pytest.fixture
def analysis_setup(engine, grounded_retriever):
    owners = []

    class OwnedSession(Session):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.owner = threading.get_ident()
            owners.append(self)

        def execute(self, *args, **kwargs):
            assert threading.get_ident() == self.owner, "Session crossed thread boundaries"
            return super().execute(*args, **kwargs)

    sessions = sessionmaker(bind=engine, class_=OwnedSession)
    with sessions.begin() as db:
        seed(db)
        db.get(Case, 2).ai_summary = "Previously approved summary."
    owners.clear()

    class Provider:
        def __init__(self):
            self.redaction_inputs = []
            self.summary_inputs = []
            self.fail_redactions = False
            self.fail_summary = False
            self.barrier = None
            self.release = None
            self.summary_done = threading.Event()

        def recommend(self, description, types, context):
            first = not self.redaction_inputs
            self.redaction_inputs.append(description)
            assert set(types) == LABELS
            assert "Protect a customer's full name" in context
            if self.barrier and first:
                self.barrier.wait(timeout=5)
                assert self.release.wait(timeout=5)
            if self.fail_redactions:
                raise RuntimeError("private provider details")
            text = "Daniel Kim" if "Daniel Kim" in description else "internal pricing"
            return AIRecommendationResponse(
                recommendations=[
                    AIRecommendation(
                        redaction_type="PERSONAL_INFO",
                        redaction_text=text,
                        starting_position=description.index(text),
                        reason="Synthetic draft",
                    ),
                    AIRecommendation(
                        redaction_type="PERSONAL_INFO",
                        redaction_text="invented span",
                        starting_position=99999,
                        reason="Invalid",
                    ),
                ]
            )

        def summarize(self, text, guidance):
            self.summary_inputs.append((json.loads(text), guidance))
            if self.barrier:
                self.barrier.wait(timeout=5)
            self.summary_done.set()
            if self.fail_summary:
                raise RuntimeError("private summary details")
            return AISummaryResponse(
                summary="Customer reported a vehicle concern; review is pending."
            )

    provider = Provider()
    graph = build_analysis_graph(sessions, provider, lambda db: grounded_retriever)
    app.dependency_overrides[analysis_graph] = lambda: graph

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(
                graph=graph,
                sessions=sessions,
                provider=provider,
                retriever=grounded_retriever,
                client=client,
                owners=owners,
            )
    finally:
        app.dependency_overrides.pop(analysis_graph, None)
        app.dependency_overrides.pop(get_db, None)


def stored_rows(sessions):
    with sessions() as db:
        return (
            list(db.execute(select(Case.__table__).order_by(Case.id))),
            list(db.execute(select(Redaction.__table__).order_by(Redaction.id))),
        )


def test_parallel_branches_share_snapshot_and_join_without_writes(analysis_setup):
    setup = analysis_setup
    before = stored_rows(setup.sessions)
    setup.owners.clear()
    setup.provider.barrier = threading.Barrier(2)
    setup.provider.release = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(setup.graph.invoke, {"case_id": 2})
        try:
            assert setup.provider.summary_done.wait(timeout=5)
            assert not future.done(), "Graph returned before recommendations finished"
        finally:
            setup.provider.release.set()
        state = future.result(timeout=10)
    assert len(setup.owners) == 3  # load, redaction retrieval, summary guidance
    assert len({id(db) for db in setup.owners}) == 3
    assert state["result"].case_id == 2
    assert [a.activity_id for a in state["result"].activities] == [3, 4]
    assert all(len(a.recommendations) == 1 for a in state["result"].activities)
    assert all(len(raw) == 2 for raw in state["raw_suggestions"].values())
    assert all(doc.metadata.get("kind") for docs in state["references"].values() for doc in docs)
    summary_notes, guidance = setup.provider.summary_inputs[0]
    assert [note["description"] for note in summary_notes] == setup.provider.redaction_inputs
    assert all(
        set(note) == {"activity_uid", "activity_type", "description"} for note in summary_notes
    )
    assert "Keep internal caps and counsel instructions out" in guidance
    assert state["summary_guidance"].metadata["kind"] == "summary_guide"
    assert stored_rows(setup.sessions) == before


def test_snapshot_is_not_reloaded_by_either_branch(analysis_setup):
    setup = analysis_setup
    original = setup.retriever.invoke
    changed = False

    def change_after_snapshot(description):
        nonlocal changed
        if not changed:
            with setup.sessions.begin() as db:
                db.get(Activity, 3).description = "Changed after snapshot loading."
            changed = True
        return original(description)

    setup.retriever.invoke = change_after_snapshot
    state = setup.graph.invoke({"case_id": 2})
    assert "Daniel Kim" in state["activities"][0].description
    assert "Daniel Kim" in setup.provider.redaction_inputs[0]
    assert "Daniel Kim" in setup.provider.summary_inputs[0][0][0]["description"]


@pytest.mark.parametrize("failure", ["redaction", "summary", "guidance", "retrieval"])
def test_failures_return_no_partial_result_or_writes(analysis_setup, failure):
    setup = analysis_setup
    if failure == "redaction":
        setup.provider.fail_redactions = True
    elif failure == "summary":
        setup.provider.fail_summary = True
    elif failure == "guidance":
        with setup.sessions.begin() as db:
            db.execute(
                delete(ReferenceChunk).where(
                    ReferenceChunk.id == chunk_id("4. Case summary style guide")
                )
            )
    else:
        setup.retriever.error = RuntimeError("private retrieval details")
    before = stored_rows(setup.sessions)
    response = setup.client.post("/cases/2/analyze")
    assert response.status_code == (502 if failure in {"redaction", "summary"} else 503)
    assert "private" not in response.text
    assert "activities" not in response.json()
    assert stored_rows(setup.sessions) == before


def test_unknown_closed_empty_and_input_limits(analysis_setup):
    setup = analysis_setup
    assert setup.client.post("/cases/99999/analyze").status_code == 404
    assert setup.client.post("/cases/3/analyze").status_code == 409
    with setup.sessions.begin() as db:
        empty = Case(case_number="EMPTY", status="OPEN")
        db.add(empty)
        db.flush()
        empty_id = empty.id
    assert setup.client.post(f"/cases/{empty_id}/analyze").json() == {
        "case_id": empty_id,
        "activities": [],
        "summary_draft": None,
    }
    assert setup.provider.redaction_inputs == setup.provider.summary_inputs == []
    with setup.sessions.begin() as db:
        db.get(Activity, 3).description = "x" * 12001
    assert setup.client.post("/cases/2/analyze").status_code == 422


def test_approval_is_explicit_independent_and_protects_saved_summary(analysis_setup):
    setup = analysis_setup
    response = setup.client.post("/cases/2/analyze")
    assert response.status_code == 200
    rec = response.json()["activities"][0]["recommendations"][0]
    assert setup.client.post("/activities/3/ai-recommendations/accept", json=rec).status_code == 201
    with setup.sessions() as db:
        assert db.get(Case, 2).ai_summary == "Previously approved summary."
        redactions = list(db.scalars(select(Redaction.id)))
    path = "/cases/2/summary/approve"
    assert (
        setup.client.post(
            path, json={"summary": "Edited and approved.", "expected_summary": None}
        ).status_code
        == 409
    )
    approved = setup.client.post(
        path,
        json={
            "summary": "Edited and approved.",
            "expected_summary": "Previously approved summary.",
        },
    )
    assert approved.status_code == 200 and approved.json()["ai_summary"] == "Edited and approved."
    assert setup.client.get("/cases/2").json()["ai_summary"] == "Edited and approved."
    with setup.sessions() as db:
        assert list(db.scalars(select(Redaction.id))) == redactions
    assert (
        setup.client.post(
            path, json={"summary": "   ", "expected_summary": "Edited and approved."}
        ).status_code
        == 422
    )
    assert (
        setup.client.post(
            "/cases/99999/summary/approve", json={"summary": "x", "expected_summary": None}
        ).status_code
        == 404
    )
    assert (
        setup.client.post(
            "/cases/3/summary/approve", json={"summary": "x", "expected_summary": None}
        ).status_code
        == 409
    )
    assert setup.client.post("/cases/2/ai-summary").status_code == 410


def test_summary_prompt_uses_guidance_not_redactions(monkeypatch):
    from app import ai_service

    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def chat_completion(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"summary":"Customer reported a vehicle concern."}'
                        )
                    )
                ]
            )

    monkeypatch.setattr(ai_service, "InferenceClient", Client)
    monkeypatch.setattr(
        ai_service,
        "get_settings",
        lambda: SimpleNamespace(hf_token="fake", hf_provider="nscale", hf_model="Qwen/Qwen3-32B"),
    )
    result = ai_service.HuggingFaceRecommendationProvider().summarize("ACTUAL NOTES", "STYLE GUIDE")
    assert result.summary
    assert calls[0]["messages"][1]["content"] == "ACTUAL NOTES"
    prompt = calls[0]["messages"][0]["content"]
    assert (
        "STYLE GUIDE" in prompt and "Omit internal" in prompt and "counsel instructions" in prompt
    )
