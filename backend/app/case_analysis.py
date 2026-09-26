"""Request-scoped LangGraph: one snapshot, two independent draft branches, one join."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.ai_grounding import LABELS, MAX_DESCRIPTION_CHARS, GroundingContext
from app.ai_service import RecommendationProvider
from app.models import Activity, Case, RedactionType, ReferenceChunk
from app.recommendation_service import retrieve_grounding, validate_suggestions
from app.reference_corpus import SOURCE, chunk_id
from app.reference_embeddings import model_key
from app.reference_service import IndexUnavailable
from app.schemas import (
    ActivityAnalysisDraft,
    AIRecommendation,
    CaseAnalysisDraft,
    GroundedAIRecommendation,
)


@dataclass(frozen=True)
class ActivitySnapshot:
    id: int
    activity_uid: str
    activity_type: str
    description: str
    saved_spans: tuple[tuple[str, int], ...]


class AnalysisInput(TypedDict):
    case_id: int


class AnalysisState(TypedDict, total=False):
    case_id: int
    activities: tuple[ActivitySnapshot, ...]
    allowed_types: tuple[str, ...]
    references: dict[int, list[Document]]
    grounding: dict[int, GroundingContext]
    raw_suggestions: dict[int, list[AIRecommendation]]
    validated_suggestions: dict[int, list[GroundedAIRecommendation]]
    summary_guidance: Document | None
    summary_draft: str | None
    result: CaseAnalysisDraft


class AnalysisFailure(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def build_analysis_graph(
    sessions: Callable[[], Session],
    provider: RecommendationProvider,
    retrievers: Callable[[Session], BaseRetriever],
) -> CompiledStateGraph:
    def load_case(state: AnalysisState) -> AnalysisState:
        with sessions() as db:
            if db.get_bind().dialect.name == "postgresql":
                db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            case = db.scalar(
                select(Case)
                .where(Case.id == state["case_id"])
                .options(selectinload(Case.activities).selectinload(Activity.redactions))
            )
            if case is None:
                raise AnalysisFailure(404, "Case not found")
            if case.status == "CLOSED":
                raise AnalysisFailure(409, "Closed cases cannot be analyzed")
            activities = tuple(
                ActivitySnapshot(
                    id=a.id,
                    activity_uid=a.activity_uid,
                    activity_type=a.activity_type,
                    description=a.description,
                    saved_spans=tuple(
                        (r.redaction_text, r.starting_position) for r in a.redactions
                    ),
                )
                for a in sorted(case.activities, key=lambda a: (a.created_at, a.id))
            )
            if (
                len(activities) > 20
                or sum(len(a.description) for a in activities) > 48000
                or any(len(a.description) > MAX_DESCRIPTION_CHARS for a in activities)
            ):
                raise AnalysisFailure(422, "Case exceeds the analysis input limit")
            types = tuple(
                db.scalars(
                    select(RedactionType.name)
                    .where(RedactionType.deleted_at.is_(None), RedactionType.name.in_(LABELS))
                    .order_by(RedactionType.name)
                )
            )
        return {"activities": activities, "allowed_types": types}

    def retrieve_rules(state: AnalysisState) -> AnalysisState:
        references, grounding = {}, {}
        if state["activities"]:
            try:
                # A session owned only by this node; never placed into graph state.
                with sessions() as db:
                    retriever = retrievers(db)
                    for activity in state["activities"]:
                        references[activity.id], grounding[activity.id] = retrieve_grounding(
                            activity, retriever
                        )
            except (IndexUnavailable, SQLAlchemyError, OSError, ValueError, RuntimeError) as exc:
                raise AnalysisFailure(503, "Redaction reference retrieval is unavailable") from exc
        return {"references": references, "grounding": grounding}

    def recommend(state: AnalysisState) -> AnalysisState:
        raw = {}
        try:
            for activity in state["activities"]:
                raw[activity.id] = provider.recommend(
                    activity.description,
                    list(state["allowed_types"]),
                    state["grounding"][activity.id].text,
                ).recommendations
        except Exception as exc:
            raise AnalysisFailure(502, "AI recommendation service is unavailable") from exc
        return {"raw_suggestions": raw}

    def validate(state: AnalysisState) -> AnalysisState:
        return {
            "validated_suggestions": {
                activity.id: validate_suggestions(
                    activity,
                    state["allowed_types"],
                    state["raw_suggestions"][activity.id],
                    state["grounding"][activity.id],
                    set(activity.saved_spans),
                )
                for activity in state["activities"]
            }
        }

    def load_summary_guidance(state: AnalysisState) -> AnalysisState:
        if not state["activities"]:
            return {"summary_guidance": None}
        try:
            with sessions() as db:
                row = db.get(ReferenceChunk, chunk_id("4. Case summary style guide"))
                if (
                    row is None
                    or row.source != SOURCE
                    or row.model_key != model_key()
                    or row.chunk_metadata.get("kind") != "summary_guide"
                    or not row.content.strip()
                    or len(row.content) > 6000
                ):
                    raise IndexUnavailable("Summary guidance unavailable")
                guidance = Document(
                    id=row.id, page_content=row.content, metadata=row.chunk_metadata
                )
        except (IndexUnavailable, SQLAlchemyError) as exc:
            raise AnalysisFailure(
                503, "Summary guidance is unavailable; re-ingest the corpus"
            ) from exc
        return {"summary_guidance": guidance}

    def draft_summary(state: AnalysisState) -> AnalysisState:
        if not state["activities"]:
            return {"summary_draft": None}
        # Only original notes from the same snapshot. Never read raw/validated
        # suggestions, saved redactions, or an existing approved summary here.
        text = json.dumps(
            [
                {
                    "activity_uid": a.activity_uid,
                    "activity_type": a.activity_type,
                    "description": a.description,
                }
                for a in state["activities"]
            ],
            ensure_ascii=False,
        )
        try:
            guidance = state["summary_guidance"]
            assert guidance is not None
            summary = provider.summarize(text, guidance.page_content).summary
            if not summary.strip() or len(summary) > 4000:
                raise ValueError("Invalid summary draft")
        except Exception as exc:
            raise AnalysisFailure(502, "AI summary service is unavailable") from exc
        return {"summary_draft": summary}

    def return_drafts(state: AnalysisState) -> AnalysisState:
        return {
            "result": CaseAnalysisDraft(
                case_id=state["case_id"],
                summary_draft=state["summary_draft"],
                activities=[
                    ActivityAnalysisDraft(
                        activity_id=a.id, recommendations=state["validated_suggestions"][a.id]
                    )
                    for a in state["activities"]
                ],
            )
        }

    graph = StateGraph(AnalysisState, input_schema=AnalysisInput)
    for name, node in (
        ("load_case", load_case),
        ("retrieve_rules", retrieve_rules),
        ("recommend", recommend),
        ("validate", validate),
        ("load_summary_guidance", load_summary_guidance),
        ("draft_summary", draft_summary),
        ("return_drafts", return_drafts),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "load_case")
    graph.add_edge("load_case", "retrieve_rules")
    graph.add_edge("load_case", "load_summary_guidance")
    graph.add_edge("retrieve_rules", "recommend")
    graph.add_edge("recommend", "validate")
    graph.add_edge("load_summary_guidance", "draft_summary")
    graph.add_edge(["validate", "draft_summary"], "return_drafts")
    graph.add_edge("return_drafts", END)
    return graph.compile()
