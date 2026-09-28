from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Port 6543 is Supabase's transaction pooler: PgBouncer in transaction mode
# breaks session-level DDL (SET/CREATE EXTENSION) that Alembic needs. Port 5432
# (session pooler or direct connection) is fine.
_TRANSACTION_POOLER_PORTS = {"6543"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str
    google_api_key: str
    openai_api_key: str
    openai_embedding_model: str
    openai_embedding_dimensions: int
    # NoDecode skips pydantic-settings' JSON parsing of complex fields so the
    # raw comma-separated string reaches the validator below.
    allowed_origins: Annotated[list[str], NoDecode]

    @field_validator("database_url")
    @classmethod
    def reject_transaction_pooler_url(cls, value: str) -> str:
        host = urlparse(value).hostname or ""
        port = urlparse(value).port
        if host.endswith("pooler.supabase.com") and str(port) in _TRANSACTION_POOLER_PORTS:
            raise ValueError(
                "DATABASE_URL must not use Supabase's transaction pooler "
                "(pooler.supabase.com:6543). Use the session pooler "
                "(pooler.supabase.com:5432) or the direct connection "
                "(db.<project-ref>.supabase.co:5432) — both keep session-level "
                "state, which migrations require."
            )
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if not origins:
                raise ValueError("ALLOWED_ORIGINS must include at least one origin")
            return origins
        return value

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return "postgresql+psycopg://" + self.database_url.removeprefix(
                "postgresql://"
            )
        return self.database_url


settings = Settings()
