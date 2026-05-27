from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    sec_user_agent: str = Field(
        default="Signal Scribe contact@example.com",
        description="SEC-required User-Agent with app/company name and contact email.",
    )
    sec_requests_per_second: float = 8.0
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    signal_scribe_api_key: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    local_store_path: str = ".signal_scribe_store.jsonl"

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
