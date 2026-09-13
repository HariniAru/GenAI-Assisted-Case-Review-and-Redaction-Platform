from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class HealthResponse(BaseModel):
    status: str


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_number: str
    status: str
    ai_summary: str | None
    created_at: datetime
    updated_at: datetime


class RedactionTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    first_name: str
    last_name: str


class RedactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    redaction_text: str
    starting_position: int
    created_at: datetime
    updated_at: datetime
    redaction_type: RedactionTypeResponse
    user: UserResponse

    @computed_field
    @property
    def ending_position(self) -> int:
        return self.starting_position + len(self.redaction_text)


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    activity_uid: str
    activity_type: str
    description: str
    created_at: datetime
    redactions: list[RedactionResponse]


class RedactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    redaction_type_id: int
    redaction_text: str
    starting_position: int


class RedactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    redaction_type_id: int | None = None
    redaction_text: str | None = None
    starting_position: int | None = None


class AIRecommendation(BaseModel):
    redaction_type: str = Field(description="One of the available redaction type names")
    redaction_text: str = Field(description="Exact contiguous substring copied from the source")
    starting_position: int = Field(description="Zero-based Unicode code-point index")
    reason: str = Field(description="Brief reviewer-facing reason")


class AIRecommendationResponse(BaseModel):
    recommendations: list[AIRecommendation]


class AISummaryResponse(BaseModel):
    summary: str
