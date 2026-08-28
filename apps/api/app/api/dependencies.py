from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import AuthenticatedActor, AuthenticationError, JwtVerifier
from app.core.database import Database, database_from_app_state
from app.core.errors import ApiError

bearer_scheme = HTTPBearer(auto_error=False)


def _jwt_verifier(request: Request) -> JwtVerifier:
    verifier: Any = request.app.state.jwt_verifier
    if not isinstance(verifier, JwtVerifier):
        raise RuntimeError("application JWT verifier is not configured")
    return verifier


async def require_authenticated_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[JwtVerifier, Depends(_jwt_verifier)],
) -> AuthenticatedActor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(
            status_code=401,
            code="authentication_required",
            message="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await verifier.verify(credentials.credentials)
    except AuthenticationError as exc:
        raise ApiError(
            status_code=401,
            code="invalid_token",
            message="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_database(request: Request) -> Database:
    return database_from_app_state(request.app.state)


CurrentActor = Annotated[AuthenticatedActor, Depends(require_authenticated_actor)]
CurrentDatabase = Annotated[Database, Depends(get_database)]
