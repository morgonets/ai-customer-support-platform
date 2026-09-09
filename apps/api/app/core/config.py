from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    knowledge_local_storage_path: Path = Path(".data/knowledge")
    knowledge_max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)
    knowledge_max_pdf_pages: int = Field(default=100, ge=1, le=100)
    knowledge_processing_stale_seconds: int = Field(default=900, ge=60, le=3600)
    knowledge_allow_local_storage_in_production: bool = False
    rag_worker_database_url: str = (
        "postgresql+psycopg://rag_worker_login:replace-with-a-local-rag-worker-password@"
        "127.0.0.1:54322/postgres"
    )
    rag_embedding_profile_key: str = "deterministic-local-v1"
    rag_generation_provider: Literal["deterministic", "openai"] = "deterministic"
    rag_exact_vector_search: bool = True
    rag_minimum_vector_similarity: float = Field(default=0.35, ge=-1, le=1)
    rag_candidate_limit: int = Field(default=20, ge=1, le=100)
    rag_evidence_limit: int = Field(default=8, ge=1, le=20)
    rag_maximum_chunks_per_source: int = Field(default=3, ge=1, le=10)
    rag_worker_lease_seconds: int = Field(default=900, ge=30, le=3600)
    rag_worker_maximum_attempts: int = Field(default=3, ge=1, le=10)
    rag_worker_retry_delay_seconds: int = Field(default=30, ge=1, le=3600)
    rag_worker_poll_seconds: float = Field(default=2, ge=0.1, le=60)
    openai_api_key: SecretStr | None = None
    openai_api_base_url: str = "https://api.openai.com/v1"
    openai_generation_model: str = "gpt-5-mini"

    @model_validator(mode="after")
    def reject_local_defaults_in_production(self) -> "Settings":
        if self.environment != "production":
            return self

        local_markers = ("127.0.0.1", "localhost", "replace-with-")
        production_values = (
            self.database_url,
            self.rag_worker_database_url,
            self.supabase_jwt_issuer,
            self.supabase_jwks_url,
        )
        if any(marker in value for marker in local_markers for value in production_values):
            raise ValueError("production database and Supabase Auth settings must be configured")
        if not self.supabase_jwt_issuer.startswith("https://"):
            raise ValueError("production Supabase JWT issuer must use HTTPS")
        if not self.supabase_jwks_url.startswith("https://"):
            raise ValueError("production Supabase JWKS URL must use HTTPS")
        if not self.knowledge_allow_local_storage_in_production:
            raise ValueError("production local knowledge storage requires explicit approval")
        if not self.knowledge_local_storage_path.is_absolute():
            raise ValueError("production local knowledge storage path must be absolute")
        if self.rag_generation_provider == "deterministic":
            raise ValueError("production answer generation requires an external provider")
        if self.openai_api_key is None:
            raise ValueError("OPENAI_API_KEY is required for OpenAI generation")
        if not self.openai_api_base_url.startswith("https://"):
            raise ValueError("production OpenAI API base URL must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
