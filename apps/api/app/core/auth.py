import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import PyJWTError

ASYMMETRIC_JWT_ALGORITHMS = ("ES256",)


class AuthenticationError(Exception):
    """A bearer token could not establish an authenticated user."""


class SigningKeyClient(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> PyJWK: ...


@dataclass(frozen=True, slots=True)
class AuthenticatedActor:
    user_id: UUID
    email: str | None
    expires_at: datetime


class JwtVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        leeway_seconds: int = 0,
        signing_key_client: SigningKeyClient | None = None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._leeway_seconds = leeway_seconds
        self._signing_key_client = signing_key_client or PyJWKClient(jwks_url, cache_keys=True)

    async def verify(self, token: str) -> AuthenticatedActor:
        try:
            signing_key = await asyncio.to_thread(
                self._signing_key_client.get_signing_key_from_jwt, token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(ASYMMETRIC_JWT_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway_seconds,
                options={"require": ["aud", "exp", "iat", "iss", "role", "sub"]},
            )
            return self._actor_from_claims(cast(dict[str, object], claims))
        except (PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise AuthenticationError from exc

    @staticmethod
    def _actor_from_claims(claims: dict[str, object]) -> AuthenticatedActor:
        if claims["role"] != "authenticated":
            raise AuthenticationError

        email_claim = claims.get("email")
        if email_claim is not None and not isinstance(email_claim, str):
            raise AuthenticationError

        expires_at_claim = claims["exp"]
        if not isinstance(expires_at_claim, int | float) or isinstance(expires_at_claim, bool):
            raise AuthenticationError

        return AuthenticatedActor(
            user_id=UUID(str(claims["sub"])),
            email=email_claim,
            expires_at=datetime.fromtimestamp(expires_at_claim, tz=UTC),
        )
