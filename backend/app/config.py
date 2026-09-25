from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    demo_reviewer_email: str = "jordan.lee@example.com"
    llm_provider: str = "huggingface"
    hf_token: str = ""
    hf_model: str = "Qwen/Qwen3-32B"
    hf_provider: str = "nscale"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
