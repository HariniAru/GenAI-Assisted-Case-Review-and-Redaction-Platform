from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Activity, Case, Redaction
from app.schemas import ActivityResponse, CaseResponse

router = APIRouter(prefix="/cases", tags=["cases"])


def refresh_status(db: Session, case: Case) -> Case:
    if case.status != "CLOSED":
        has_redactions = db.scalar(
            select(
                exists().where(Redaction.activity_id == Activity.id, Activity.case_id == case.id)
            )
        )
        case.status = "IN_PROGRESS" if has_redactions else "OPEN"
    return case


@router.get("", response_model=list[CaseResponse])
def list_cases(db: Session = Depends(get_db)) -> list[Case]:  # noqa: B008
    return [
        refresh_status(db, case)
        for case in db.scalars(select(Case).order_by(Case.case_number)).all()
    ]


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: int, db: Session = Depends(get_db)) -> Case:  # noqa: B008
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return refresh_status(db, case)


@router.post("/{case_id}/close", response_model=CaseResponse)
def close_case(case_id: int, db: Session = Depends(get_db)) -> Case:  # noqa: B008
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, f"Case {case_id} not found")
    case.status = "CLOSED"
    db.commit()
    return case


@router.post("/{case_id}/reopen", response_model=CaseResponse)
def reopen_case(case_id: int, db: Session = Depends(get_db)) -> Case:  # noqa: B008
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, f"Case {case_id} not found")
    case.status = "OPEN"
    refresh_status(db, case)
    db.commit()
    return case


@router.get("/{case_id}/activities", response_model=list[ActivityResponse])
def list_activities(case_id: int, db: Session = Depends(get_db)) -> list[Activity]:  # noqa: B008
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    activities = list(
        db.scalars(
            select(Activity)
            .where(Activity.case_id == case_id)
            .options(
                selectinload(Activity.redactions).selectinload(Redaction.redaction_type),
                selectinload(Activity.redactions).selectinload(Redaction.user),
            )
            .order_by(Activity.created_at, Activity.id)
        ).all()
    )
    for activity in activities:
        activity.redactions.sort(key=lambda redaction: (redaction.starting_position, redaction.id))
    return activities
