from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.knowledge_errors import knowledge_error_handler
from app.api.rag_errors import rag_error_handler
from app.api.router import api_router
from app.api.tenant_errors import tenant_error_handler
from app.core.auth import JwtVerifier
from app.core.config import get_settings
from app.core.database import Database
from app.core.errors import ApiError, api_error_handler, validation_error_handler
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.knowledge.errors import KnowledgeError
from app.knowledge.extraction import DocumentExtractor
from app.knowledge.repository import SqlAlchemyKnowledgeRepository
from app.knowledge.storage import LocalObjectStorage
from app.rag.errors import RagError
from app.rag.ports import EmbeddingProvider, GenerationProvider
from app.rag.providers import (
    DeterministicEmbeddingProvider,
    DeterministicGenerationProvider,
    LoggingRagTelemetry,
    OpenAIEmbeddingProvider,
    OpenAIGenerationProvider,
)
from app.rag.repository import RagRepository
from app.rag.service import RagService
from app.tenants.authorization import TenantAuthorizer
from app.tenants.errors import TenantError
from app.tenants.repository import SqlAlchemyTenantRepository


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        await application.state.database.dispose()

    application = FastAPI(
        title=settings.app_name,
        summary="Tenant-aware API for the AI Customer Support Platform.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.database = Database(settings.database_url)
    application.state.jwt_verifier = JwtVerifier(
        issuer=settings.supabase_jwt_issuer,
        audience=settings.supabase_jwt_audience,
        jwks_url=settings.supabase_jwks_url,
        leeway_seconds=settings.supabase_jwt_leeway_seconds,
    )
    application.state.knowledge_storage = LocalObjectStorage(settings.knowledge_local_storage_path)
    application.state.document_extractor = DocumentExtractor(
        maximum_pdf_pages=settings.knowledge_max_pdf_pages
    )
    embedding_providers: dict[str, EmbeddingProvider] = {
        "deterministic": DeterministicEmbeddingProvider()
    }
    generation_provider: GenerationProvider = DeterministicGenerationProvider()
    if settings.openai_api_key is not None:
        api_key = settings.openai_api_key.get_secret_value()
        embedding_providers["openai"] = OpenAIEmbeddingProvider(
            api_key, base_url=settings.openai_api_base_url
        )
        if settings.rag_generation_provider == "openai":
            generation_provider = OpenAIGenerationProvider(
                api_key,
                model=settings.openai_generation_model,
                base_url=settings.openai_api_base_url,
            )
    application.state.rag_service = RagService(
        RagRepository(),
        SqlAlchemyKnowledgeRepository(),
        TenantAuthorizer(SqlAlchemyTenantRepository()),
        embedding_providers,
        generation_provider,
        LoggingRagTelemetry(),
        default_profile_key=settings.rag_embedding_profile_key,
        minimum_vector_similarity=settings.rag_minimum_vector_similarity,
        candidate_limit=settings.rag_candidate_limit,
        evidence_limit=settings.rag_evidence_limit,
        maximum_per_source=settings.rag_maximum_chunks_per_source,
        exact_vector_search=settings.rag_exact_vector_search,
    )
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(TenantError, tenant_error_handler)
    application.add_exception_handler(KnowledgeError, knowledge_error_handler)
    application.add_exception_handler(RagError, rag_error_handler)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router)
    return application


app = create_app()
