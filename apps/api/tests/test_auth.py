import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from jwt import PyJWK
from jwt.algorithms import ECAlgorithm

from app.api.dependencies import _jwt_verifier, get_database, require_authenticated_actor
from app.core.auth import AuthenticatedActor, AuthenticationError, JwtVerifier
from app.core.database import Database
from app.core.errors import ApiError
from app.main import app

ISSUER = "https://project.supabase.co/auth/v1"
AUDIENCE = "authenticated"


class StaticSigningKeyClient:
    def __init__(self, signing_key: PyJWK) -> None:
        self._signing_key = signing_key

    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        del token
        return self._signing_key


class RaisingSigningKeyClient:
    def get_signing_key_from_jwt(self, token: str) -> PyJWK:
        del token
        raise ValueError("no matching signing key")


class StubVerifier(JwtVerifier):
    def __init__(
        self, actor: AuthenticatedActor | None = None, error: AuthenticationError | None = None
    ) -> None:
        self._actor = actor
        self._error = error

    async def verify(self, token: str) -> AuthenticatedActor:
        assert token
        if self._error is not None:
            raise self._error
        assert self._actor is not None
        return self._actor


def _key_material() -> tuple[ec.EllipticCurvePrivateKey, PyJWK]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return private_key, PyJWK.from_dict(public_jwk, algorithm="ES256")


def _claims(user_id: UUID, **overrides: object) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    claims: dict[str, Any] = {
        "aud": AUDIENCE,
        "email": "person@example.com",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "iss": ISSUER,
        "role": "authenticated",
        "sub": str(user_id),
    }
    claims.update(overrides)
    return claims


def test_jwt_verifier_accepts_valid_asymmetric_supabase_token() -> None:
    user_id = uuid4()
    private_key, signing_key = _key_material()
    token = jwt.encode(_claims(user_id), private_key, algorithm="ES256")
    verifier = JwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://unused.example/jwks.json",
        signing_key_client=StaticSigningKeyClient(signing_key),
    )

    actor = asyncio.run(verifier.verify(token))

    assert actor.user_id == user_id
    assert actor.email == "person@example.com"
    assert actor.expires_at > datetime.now(tz=UTC)


@pytest.mark.parametrize(
    "overrides",
    [
        {"role": "anon"},
        {"sub": "not-a-uuid"},
        {"email": 7},
    ],
)
def test_jwt_verifier_rejects_invalid_identity_claims(overrides: dict[str, object]) -> None:
    private_key, signing_key = _key_material()
    token = jwt.encode(_claims(uuid4(), **overrides), private_key, algorithm="ES256")
    verifier = JwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://unused.example/jwks.json",
        signing_key_client=StaticSigningKeyClient(signing_key),
    )

    with pytest.raises(AuthenticationError):
        asyncio.run(verifier.verify(token))


def test_actor_claim_parsing_accepts_missing_email_and_rejects_invalid_expiry() -> None:
    claims: dict[str, object] = {
        "role": "authenticated",
        "sub": str(uuid4()),
        "exp": 1_900_000_000,
    }
    assert JwtVerifier._actor_from_claims(claims).email is None

    claims["exp"] = True
    with pytest.raises(AuthenticationError):
        JwtVerifier._actor_from_claims(claims)


def test_jwt_verifier_converts_signing_key_failure_to_authentication_error() -> None:
    verifier = JwtVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        jwks_url="https://unused.example/jwks.json",
        signing_key_client=RaisingSigningKeyClient(),
    )

    with pytest.raises(AuthenticationError):
        asyncio.run(verifier.verify("untrusted-token"))


def test_current_user_requires_bearer_authentication() -> None:
    response = TestClient(app).get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "authentication_required"


def test_current_user_rejects_invalid_token() -> None:
    original_verifier = app.state.jwt_verifier
    app.state.jwt_verifier = StubVerifier(error=AuthenticationError())
    try:
        response = TestClient(app).get(
            "/api/v1/users/me", headers={"Authorization": "Bearer access-token"}
        )
    finally:
        app.state.jwt_verifier = original_verifier

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_current_user_returns_verified_actor() -> None:
    actor = AuthenticatedActor(
        user_id=uuid4(),
        email="person@example.com",
        expires_at=datetime.now(tz=UTC) + timedelta(minutes=5),
    )
    original_verifier = app.state.jwt_verifier
    app.state.jwt_verifier = StubVerifier(actor=actor)
    try:
        response = TestClient(app).get(
            "/api/v1/users/me", headers={"Authorization": "Bearer access-token"}
        )
    finally:
        app.state.jwt_verifier = original_verifier

    assert response.status_code == 200
    assert response.json() == {"id": str(actor.user_id), "email": actor.email}


def test_auth_dependency_rejects_non_bearer_scheme() -> None:
    verifier = StubVerifier()

    with pytest.raises(ApiError) as error:
        asyncio.run(
            require_authenticated_actor(
                HTTPAuthorizationCredentials(scheme="Basic", credentials="credentials"), verifier
            )
        )

    assert error.value.code == "authentication_required"


def test_application_dependencies_fail_closed_for_invalid_state() -> None:
    request = Request({"type": "http", "app": app, "headers": []})
    original_verifier = app.state.jwt_verifier
    app.state.jwt_verifier = object()
    try:
        with pytest.raises(RuntimeError, match="JWT verifier"):
            _jwt_verifier(request)
    finally:
        app.state.jwt_verifier = original_verifier


def test_database_dependency_returns_configured_database() -> None:
    request = Request({"type": "http", "app": app, "headers": []})
    database = Database.__new__(Database)
    original_database = app.state.database
    app.state.database = database
    try:
        assert get_database(request) is database
    finally:
        app.state.database = original_database
