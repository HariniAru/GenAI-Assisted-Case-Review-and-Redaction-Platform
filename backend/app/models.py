from datetime import datetime, timezone
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


class RedactionSource(str, Enum):
    AI = "AI"
    MANUAL = "MANUAL"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    redactions: Mapped[list["Redaction"]] = relationship(back_populates="user")


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'IN_PROGRESS', 'CLOSED')", name="ck_cases_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    case_number: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    activities: Mapped[list["Activity"]] = relationship(back_populates="case")


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_case_id", "case_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    activity_uid: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    activity_type: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    case: Mapped[Case] = relationship(back_populates="activities")
    redactions: Mapped[list["Redaction"]] = relationship(back_populates="activity")


class RedactionType(Base):
    __tablename__ = "redaction_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redactions: Mapped[list["Redaction"]] = relationship(back_populates="redaction_type")


class Redaction(Base):
    __tablename__ = "redactions"
    __table_args__ = (
        CheckConstraint("source IN ('AI', 'MANUAL')", name="ck_redactions_source"),
        CheckConstraint("starting_position >= 0", name="ck_redactions_starting_position"),
        Index("ix_redactions_activity_id", "activity_id"),
        Index("ix_redactions_redaction_type_id", "redaction_type_id"),
        Index("ix_redactions_user_id", "user_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    redaction_type_id: Mapped[int] = mapped_column(ForeignKey("redaction_types.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    redaction_text: Mapped[str] = mapped_column(String, nullable=False)
    starting_position: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    activity: Mapped[Activity] = relationship(back_populates="redactions")
    redaction_type: Mapped[RedactionType] = relationship(back_populates="redactions")
    user: Mapped[User] = relationship(back_populates="redactions")


class ReferenceChunk(Base):
    __tablename__ = "reference_chunks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict[str, str]] = mapped_column("metadata", JSON, nullable=False)
    model_key: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(384).with_variant(JSON(), "sqlite"), nullable=False
    )
