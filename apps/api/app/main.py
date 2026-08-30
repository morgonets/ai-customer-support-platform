from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.tenant_errors import tenant_error_handler
from app.core.auth import JwtVerifier
from app.core.config import get_settings
from app.core.database import Database
from app.core.errors import ApiError, api_error_handler, validation_error_handler
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.tenants.errors import TenantError


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
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(TenantError, tenant_error_handler)
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
