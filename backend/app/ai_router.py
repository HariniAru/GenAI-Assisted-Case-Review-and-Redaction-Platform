from fastapi import APIRouter, Depends, HTTPException
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from langsmith import tracing_context
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.ai_grounding import LABELS, MAX_DESCRIPTION_CHARS, build_grounding, current_policy
from app.ai_service import HuggingFaceRecommendationProvider, RecommendationProvider
from app.config import get_settings
from app.database import get_db
from app.models import Activity, Redaction, RedactionType, User
from app.reference_router import embedding_provider
from app.reference_service import IndexUnavailable, ReferenceRetriever
from app.schemas import (
    AISummaryResponse,
    GroundedAIRecommendation,
    GroundedAIRecommendationResponse,
    RedactionResponse,
)

router = APIRouter(tags=["ai-recommendations"])
provider: RecommendationProvider = HuggingFaceRecommendationProvider()


@router.post("/cases/{case_id}/ai-summary", response_model=AISummaryResponse)
def summary(case_id: int, db: Session = Depends(get_db)):  # noqa: B008
    from app.models import Case

    case = db.get(Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    if case.ai_summary:
        return AISummaryResponse(summary=case.ai_summary)
    activities = db.scalars(
        select(Activity).where(Activity.case_id == case_id).order_by(Activity.id)
    ).all()
    try:
        result = provider.summarize("\n".join(a.description for a in activities))
    except Exception as exc:
        raise HTTPException(502, "AI summary service is unavailable") from exc
    case.ai_summary = result.summary
    db.commit()
    return result


def valid(activity, types, recommendation):
    typ = types.get(recommendation.redaction_type)
    start = recommendation.starting_position
    text = recommendation.redaction_text
    return (
        typ
        and text.strip()
        and start >= 0
        and start + len(text) <= len(activity.description)
        and activity.description[start : start + len(text)] == text
    )


def normalize_position(activity, recommendation):
    """Correct a model offset only when the exact text has one unambiguous match."""
    text = recommendation.redaction_text
    starts = [
        i for i in range(len(activity.description)) if activity.description.startswith(text, i)
    ]
    if len(starts) == 1 and starts[0] != recommendation.starting_position:
        return recommendation.model_copy(update={"starting_position": starts[0]})
    return recommendation


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
        with tracing_context(enabled=False):
            documents = retriever.invoke(activity.description)
        grounding = build_grounding(documents, activity.activity_uid)
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
    seen = set()
    output = []
    for rec in result.recommendations:
        rec = normalize_position(activity, rec)
        key = (rec.redaction_type, rec.redaction_text, rec.starting_position)
        duplicate = db.scalar(
            select(Redaction).where(
                Redaction.activity_id == activity_id,
                Redaction.redaction_text == rec.redaction_text,
                Redaction.starting_position == rec.starting_position,
            )
        )
        if (
            key not in seen
            and rec.redaction_type in grounding.policies
            and valid(activity, types, rec)
            and not duplicate
        ):
            seen.add(key)
            output.append(
                GroundedAIRecommendation(
                    **rec.model_dump(), supporting_policy=grounding.policies[rec.redaction_type]
                )
            )
    return GroundedAIRecommendationResponse(recommendations=output)


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
