from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_name: str = "AI Customer Support Platform API"
    environment: Environment = "local"
    log_level: str = "INFO"
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    database_url: str = (
        "postgresql+psycopg://api_login:replace-with-a-local-api-database-password@"
        "127.0.0.1:54322/postgres"
    )
    supabase_jwt_issuer: str = "http://127.0.0.1:54321/auth/v1"
    supabase_jwks_url: str = "http://127.0.0.1:54321/auth/v1/.well-known/jwks.json"
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_leeway_seconds: int = Field(default=0, ge=0, le=300)

    @model_validator(mode="after")
    def reject_local_defaults_in_production(self) -> "Settings":
        if self.environment != "production":
            return self

        local_markers = ("127.0.0.1", "localhost", "replace-with-")
        production_values = (
            self.database_url,
            self.supabase_jwt_issuer,
            self.supabase_jwks_url,
        )
        if any(marker in value for marker in local_markers for value in production_values):
            raise ValueError("production database and Supabase Auth settings must be configured")
        if not self.supabase_jwt_issuer.startswith("https://"):
            raise ValueError("production Supabase JWT issuer must use HTTPS")
        if not self.supabase_jwks_url.startswith("https://"):
            raise ValueError("production Supabase JWKS URL must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
