from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Activity, Redaction, RedactionType, User
from app.schemas import RedactionCreate, RedactionResponse, RedactionTypeResponse, RedactionUpdate

router = APIRouter(tags=["redactions"])


def validate(db, activity, type_id, text, start):
    if activity is None:
        raise HTTPException(404, "Activity not found")
    typ = db.get(RedactionType, type_id)
    if typ is None or typ.deleted_at is not None:
        raise HTTPException(422, "Redaction type is unavailable")
    if not text or not text.strip() or start < 0:
        raise HTTPException(422, "Invalid redaction text or position")
    end = start + len(text)
    if end > len(activity.description) or activity.description[start:end] != text:
        raise HTTPException(422, "Redaction text does not match the activity description")
    return typ


def ensure_case_open(activity):
    if activity.case.status == "CLOSED":
        raise HTTPException(409, "Closed cases cannot be changed")


def loaded(db, rid):
    return db.scalar(
        select(Redaction)
        .where(Redaction.id == rid)
        .options(selectinload(Redaction.redaction_type), selectinload(Redaction.user))
    )


@router.get("/redaction-types", response_model=list[RedactionTypeResponse])
def list_types(db: Session = Depends(get_db)):  # noqa: B008
    return list(
        db.scalars(
            select(RedactionType)
            .where(RedactionType.deleted_at.is_(None))
            .order_by(RedactionType.name)
        ).all()
    )


@router.post(
    "/activities/{activity_id}/redactions", response_model=RedactionResponse, status_code=201
)
def create(activity_id: int, payload: RedactionCreate, db: Session = Depends(get_db)):  # noqa: B008
    activity = db.get(Activity, activity_id)
    if activity:
        ensure_case_open(activity)
    user = db.scalar(select(User).where(User.email == get_settings().demo_reviewer_email))
    if user is None:
        raise HTTPException(500, "Configured demo reviewer does not exist")
    typ = validate(
        db, activity, payload.redaction_type_id, payload.redaction_text, payload.starting_position
    )
    duplicate = db.scalar(
        select(Redaction).where(
            Redaction.activity_id == activity_id,
            Redaction.redaction_type_id == typ.id,
            Redaction.source == "MANUAL",
            Redaction.redaction_text == payload.redaction_text,
            Redaction.starting_position == payload.starting_position,
        )
    )
    if duplicate:
        raise HTTPException(409, "An identical redaction already exists")
    item = Redaction(
        activity=activity,
        redaction_type=typ,
        user=user,
        source="MANUAL",
        redaction_text=payload.redaction_text,
        starting_position=payload.starting_position,
    )
    db.add(item)
    db.commit()
    return loaded(db, item.id)


@router.patch("/redactions/{redaction_id}", response_model=RedactionResponse)
def update(redaction_id: int, payload: RedactionUpdate, db: Session = Depends(get_db)):  # noqa: B008
    item = db.get(Redaction, redaction_id)
    if item is None:
        raise HTTPException(404, "Redaction not found")
    if item.source != "MANUAL":
        raise HTTPException(409, "AI redactions are read-only")
    ensure_case_open(item.activity)
    values = payload.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(422, "At least one editable field is required")
    typ = validate(
        db,
        item.activity,
        values.get("redaction_type_id", item.redaction_type_id),
        values.get("redaction_text", item.redaction_text),
        values.get("starting_position", item.starting_position),
    )
    item.redaction_type = typ
    item.redaction_text = values.get("redaction_text", item.redaction_text)
    item.starting_position = values.get("starting_position", item.starting_position)
    db.commit()
    return loaded(db, item.id)


@router.delete("/redactions/{redaction_id}", status_code=204)
def delete(redaction_id: int, db: Session = Depends(get_db)):  # noqa: B008
    item = db.get(Redaction, redaction_id)
    if item is None:
        raise HTTPException(404, "Redaction not found")
    ensure_case_open(item.activity)
    db.delete(item)
    db.commit()
    return Response(status_code=204)
