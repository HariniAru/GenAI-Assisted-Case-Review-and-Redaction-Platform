from fastapi import APIRouter, Depends, HTTPException
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.ai_grounding import LABELS, MAX_DESCRIPTION_CHARS, current_policy
from app.ai_service import HuggingFaceRecommendationProvider, RecommendationProvider
from app.config import get_settings
from app.database import get_db
from app.models import Activity, Redaction, RedactionType, User
from app.recommendation_service import retrieve_grounding, valid, validate_suggestions
from app.reference_router import embedding_provider
from app.reference_service import IndexUnavailable, ReferenceRetriever
from app.schemas import (
    GroundedAIRecommendation,
    GroundedAIRecommendationResponse,
    RedactionResponse,
)

router = APIRouter(tags=["ai-recommendations"])
provider: RecommendationProvider = HuggingFaceRecommendationProvider()


@router.post("/cases/{case_id}/ai-summary", deprecated=True)
def summary(case_id: int):
    raise HTTPException(410, "Use Analyze case for drafts, then explicitly approve the summary")


def recommendation_retriever(
    db: Session = Depends(get_db),  # noqa: B008
    embeddings: Embeddings = Depends(embedding_provider),  # noqa: B008
) -> BaseRetriever:
    return ReferenceRetriever(
        session=db, embeddings=embeddings, example_count=get_settings().reference_examples
    )


@router.post(
    "/activities/{activity_id}/ai-recommendations", response_model=GroundedAIRecommendationResponse
)
def recommend(
    activity_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    retriever: BaseRetriever = Depends(recommendation_retriever),  # noqa: B008
):
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(404, "Activity not found")
    if activity.case.status == "CLOSED":
        raise HTTPException(409, "Closed cases cannot be changed")
    types = {
        t.name: t
        for t in db.scalars(select(RedactionType).where(RedactionType.deleted_at.is_(None)))
    }
    if len(activity.description) > MAX_DESCRIPTION_CHARS:
        raise HTTPException(422, "Activity exceeds the AI recommendation input limit")
    try:
        _, grounding = retrieve_grounding(activity, retriever)
    except (IndexUnavailable, SQLAlchemyError, OSError, ValueError, RuntimeError):
        raise HTTPException(
            503,
            "Reference retrieval is unavailable. Check migrations, "
            "ingestion, and the local model, then retry.",
        ) from None
    try:
        result = provider.recommend(
            activity.description, sorted(set(types) & LABELS), grounding.text
        )
    except Exception as exc:
        raise HTTPException(502, "AI recommendation service is unavailable") from exc
    saved_spans = set(
        db.execute(
            select(Redaction.redaction_text, Redaction.starting_position).where(
                Redaction.activity_id == activity_id
            )
        )
    )
    return GroundedAIRecommendationResponse(
        recommendations=validate_suggestions(
            activity, list(types), result.recommendations, grounding, saved_spans
        )
    )


@router.post(
    "/activities/{activity_id}/ai-recommendations/accept",
    response_model=RedactionResponse,
    status_code=201,
)
def accept(
    activity_id: int,
    recommendation: GroundedAIRecommendation,
    db: Session = Depends(get_db),  # noqa: B008
):
    activity = db.scalar(select(Activity).where(Activity.id == activity_id).with_for_update())
    typ = db.scalar(
        select(RedactionType).where(
            RedactionType.name == recommendation.redaction_type, RedactionType.deleted_at.is_(None)
        )
    )
    user = db.scalar(select(User).where(User.email == get_settings().demo_reviewer_email))
    if not activity:
        raise HTTPException(404, "Activity not found")
    if activity.case.status == "CLOSED":
        raise HTTPException(409, "Closed cases cannot be changed")
    if (
        not typ
        or recommendation.redaction_type not in LABELS
        or not valid(activity, {typ.name: typ}, recommendation)
    ):
        raise HTTPException(422, "Recommendation does not match the activity")
    if not user:
        raise HTTPException(500, "Configured demo reviewer does not exist")
    try:
        evidence = current_policy(db, recommendation.redaction_type)
    except (IndexUnavailable, SQLAlchemyError):
        raise HTTPException(
            503, "Supporting policy is unavailable; re-ingest the reference corpus"
        ) from None
    if recommendation.supporting_policy != evidence:
        raise HTTPException(
            422, "Supporting policy changed or is invalid. Generate recommendations again."
        )
    duplicate = db.scalar(
        select(Redaction.id).where(
            Redaction.activity_id == activity_id,
            Redaction.redaction_text == recommendation.redaction_text,
            Redaction.starting_position == recommendation.starting_position,
        )
    )
    if duplicate is not None:
        raise HTTPException(409, "An identical redaction already exists")
    # The client-supplied reason is advisory text only; it is never persisted
    # or used as authority to accept a span. Evidence is verified above.
    item = Redaction(
        activity=activity,
        redaction_type=typ,
        user=user,
        source="AI",
        redaction_text=recommendation.redaction_text,
        starting_position=recommendation.starting_position,
    )
    db.add(item)
    db.commit()
    return db.scalar(
        select(Redaction)
        .where(Redaction.id == item.id)
        .options(selectinload(Redaction.redaction_type), selectinload(Redaction.user))
    )
