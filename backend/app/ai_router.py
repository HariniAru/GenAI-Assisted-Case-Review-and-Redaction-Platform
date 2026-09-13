from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai_service import HuggingFaceRecommendationProvider, RecommendationProvider
from app.config import get_settings
from app.database import get_db
from app.models import Activity, Redaction, RedactionType, User
from app.schemas import (
    AIRecommendation,
    AIRecommendationResponse,
    AISummaryResponse,
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


@router.post(
    "/activities/{activity_id}/ai-recommendations", response_model=AIRecommendationResponse
)
def recommend(activity_id: int, db: Session = Depends(get_db)):  # noqa: B008
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(404, "Activity not found")
    if activity.case.status == "CLOSED":
        raise HTTPException(409, "Closed cases cannot be changed")
    types = {
        t.name: t
        for t in db.scalars(select(RedactionType).where(RedactionType.deleted_at.is_(None)))
    }
    try:
        result = provider.recommend(activity.description, list(types))
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
        if key not in seen and valid(activity, types, rec) and not duplicate:
            seen.add(key)
            output.append(rec)
    return AIRecommendationResponse(recommendations=output)


@router.post(
    "/activities/{activity_id}/ai-recommendations/accept",
    response_model=RedactionResponse,
    status_code=201,
)
def accept(activity_id: int, recommendation: AIRecommendation, db: Session = Depends(get_db)):  # noqa: B008
    activity = db.get(Activity, activity_id)
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
    if not typ or not valid(activity, {typ.name: typ}, recommendation):
        raise HTTPException(422, "Recommendation does not match the activity")
    if not user:
        raise HTTPException(500, "Configured demo reviewer does not exist")
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
