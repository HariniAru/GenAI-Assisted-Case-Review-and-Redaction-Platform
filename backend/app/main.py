from fastapi import FastAPI

from app.ai_router import router as ai_router
from app.case_router import router as case_router
from app.redaction_router import router as redaction_router
from app.reference_router import router as reference_router
from app.schemas import HealthResponse

app = FastAPI(title="GenAI Case Review API")
app.include_router(case_router)
app.include_router(redaction_router)
app.include_router(ai_router)
app.include_router(reference_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
