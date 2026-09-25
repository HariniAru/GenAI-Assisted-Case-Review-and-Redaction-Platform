from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    demo_reviewer_email: str = "jordan.lee@example.com"
    llm_provider: str = "huggingface"
    hf_token: str = ""
    hf_model: str = "Qwen/Qwen3-32B"
    hf_provider: str = "nscale"

    embedding_model: Literal["sentence-transformers/all-MiniLM-L6-v2"] = (
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    embedding_revision: Literal["1110a243fdf4706b3f48f1d95db1a4f5529b4d41"] = (
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    )
    embedding_dimensions: Literal[384] = 384
    reference_examples: int = Field(default=3, ge=1, le=5)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
