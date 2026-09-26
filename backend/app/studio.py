"""Studio uses the same draft-only graph as the FastAPI analysis endpoint."""

from app.analysis_router import analysis_graph
from app.config import get_settings

if not get_settings().database_url.startswith("postgresql+psycopg://"):
    raise RuntimeError("Studio requires the PostgreSQL DATABASE_URL from .env.postgres")

graph = analysis_graph()
