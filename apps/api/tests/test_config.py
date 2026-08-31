import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.core.config import Settings


def test_settings_parse_cors_origins_from_json_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("API_CORS_ORIGINS", '["https://support.example.com"]')

    settings = Settings()

    assert settings.api_cors_origins == ["https://support.example.com"]


def test_non_production_settings_allow_local_services() -> None:
    assert Settings(environment="test").environment == "test"


@pytest.mark.parametrize(
    ("database_url", "issuer", "jwks_url", "message"),
    [
        (
            "postgresql+psycopg://api_login:replace-with-secret@db.example/postgres",
            "https://project.supabase.co/auth/v1",
            "https://project.supabase.co/auth/v1/.well-known/jwks.json",
            "must be configured",
        ),
        (
            "postgresql+psycopg://api_login:secret@db.example/postgres",
            "http://project.supabase.co/auth/v1",
            "https://project.supabase.co/auth/v1/.well-known/jwks.json",
            "issuer must use HTTPS",
        ),
        (
            "postgresql+psycopg://api_login:secret@db.example/postgres",
            "https://project.supabase.co/auth/v1",
            "http://project.supabase.co/auth/v1/.well-known/jwks.json",
            "JWKS URL must use HTTPS",
        ),
    ],
)
def test_production_settings_reject_unsafe_auth_or_database_configuration(
    database_url: str, issuer: str, jwks_url: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            environment="production",
            database_url=database_url,
            supabase_jwt_issuer=issuer,
            supabase_jwks_url=jwks_url,
        )


def test_production_settings_accept_configured_https_services() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://api_login:secret@db.example/postgres",
        supabase_jwt_issuer="https://project.supabase.co/auth/v1",
        supabase_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
        knowledge_allow_local_storage_in_production=True,
        knowledge_local_storage_path="/var/lib/ai-support/knowledge",
    )

    assert settings.environment == "production"


@pytest.mark.parametrize(
    ("allow_local", "storage_path", "message"),
    [
        (False, "/var/lib/ai-support/knowledge", "requires explicit approval"),
        (True, ".data/knowledge", "path must be absolute"),
    ],
)
def test_production_settings_reject_unsafe_local_knowledge_storage(
    allow_local: bool, storage_path: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            environment="production",
            database_url="postgresql+psycopg://api_login:secret@db.example/postgres",
            supabase_jwt_issuer="https://project.supabase.co/auth/v1",
            supabase_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            knowledge_allow_local_storage_in_production=allow_local,
            knowledge_local_storage_path=storage_path,
        )
