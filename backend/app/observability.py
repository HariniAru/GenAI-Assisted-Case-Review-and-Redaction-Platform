"""Opt-in tracing using Settings, including values from the local .env file."""

from functools import lru_cache

from langsmith import Client, tracing_context

from app.config import get_settings


@lru_cache
def tracing_client() -> Client:
    settings = get_settings()
    return Client(
        api_key=settings.langsmith_api_key.get_secret_value(),
        api_url=settings.langsmith_endpoint,
        workspace_id=settings.langsmith_workspace_id,
    )


def analysis_tracing():
    settings = get_settings()
    if not settings.langsmith_tracing:
        return tracing_context(enabled=False)
    return tracing_context(
        enabled=True,
        client=tracing_client(),
        project_name=settings.langsmith_project,
        tags=["case-analysis", "synthetic-data"],
    )
