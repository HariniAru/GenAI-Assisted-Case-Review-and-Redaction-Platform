from fastapi import APIRouter, Depends, HTTPException
from langgraph.graph.state import CompiledStateGraph
from langsmith import tracing_context
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import ai_router
from app.case_analysis import AnalysisFailure, build_analysis_graph
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import Case
from app.reference_router import embedding_provider
from app.reference_service import ReferenceRetriever
from app.schemas import CaseAnalysisDraft, CaseResponse, SummaryApproval

router = APIRouter(prefix="/cases", tags=["case-analysis"])


def analysis_graph() -> CompiledStateGraph:
    return build_analysis_graph(
        SessionLocal,
        ai_router.provider,
        lambda db: ReferenceRetriever(
            session=db,
            embeddings=embedding_provider(),
            example_count=get_settings().reference_examples,
        ),
    )


@router.post("/{case_id}/analyze", response_model=CaseAnalysisDraft)
def analyze(case_id: int, graph: CompiledStateGraph = Depends(analysis_graph)):  # noqa: B008
    try:
        with tracing_context(enabled=False):
            state = graph.invoke({"case_id": case_id}, config={"max_concurrency": 2})
        return state["result"]
    except AnalysisFailure as exc:
        raise HTTPException(exc.status, exc.detail) from None
    except SQLAlchemyError:
        raise HTTPException(503, "Case analysis database is unavailable") from None


@router.post("/{case_id}/summary/approve", response_model=CaseResponse)
def approve_summary(
    case_id: int,
    payload: SummaryApproval,
    db: Session = Depends(get_db),  # noqa: B008
) -> Case:
    case = db.scalar(select(Case).where(Case.id == case_id).with_for_update())
    if case is None:
        raise HTTPException(404, "Case not found")
    if case.status == "CLOSED":
        raise HTTPException(409, "Closed cases cannot be changed")
    if not payload.summary.strip():
        raise HTTPException(422, "Summary must contain text")
    if case.ai_summary != payload.expected_summary:
        raise HTTPException(409, "Saved summary changed; reload the case before approving")
    case.ai_summary = payload.summary
    db.commit()
    return case
