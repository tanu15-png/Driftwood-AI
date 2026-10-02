import pytest
from pydantic import ValidationError

from app.config import Settings

_REQUIRED = {
    "supabase_url": "https://example.supabase.co",
    "supabase_anon_key": "anon",
    "supabase_service_role_key": "service",
    "allowed_origins": "http://localhost:5173",
}


def test_embedding_model_defaults_to_local_bge() -> None:
    settings = Settings(
        **_REQUIRED,
        database_url="postgresql://postgres:pass@db.example.supabase.co:5432/postgres",
    )
    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"


def test_cohere_api_key_defaults_to_empty() -> None:
    """No COHERE_API_KEY → optional reranker is disabled, settings still valid."""

    settings = Settings(
        **_REQUIRED,
        database_url="postgresql://postgres:pass@db.example.supabase.co:5432/postgres",
    )
    assert settings.cohere_api_key == ""


def test_splits_comma_separated_origins() -> None:
    settings = Settings(
        **(_REQUIRED | {"allowed_origins": "http://localhost:5173, http://127.0.0.1:5173"}),
        database_url="postgresql://postgres:pass@db.example.supabase.co:5432/postgres",
    )
    assert settings.allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_rejects_transaction_pooler_database_url() -> None:
    with pytest.raises(ValidationError):
        Settings(
            **_REQUIRED,
            database_url=(
                "postgresql://postgres:pass@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
            ),
        )


def test_allows_session_pooler_database_url() -> None:
    """Session pooler (port 5432) is the IPv4-compatible path for migrations."""

    settings = Settings(
        **_REQUIRED,
        database_url=(
            "postgresql://postgres.ref:pass@aws-0-us-east-1.pooler.supabase.com:5432/postgres"
        ),
    )
    assert settings.sqlalchemy_database_url.startswith("postgresql+psycopg://")


def test_uses_psycopg_driver_in_sqlalchemy_url() -> None:
    settings = Settings(
        **_REQUIRED,
        database_url="postgresql://postgres:pass@db.example.supabase.co:5432/postgres",
    )
    assert settings.sqlalchemy_database_url.startswith("postgresql+psycopg://")
