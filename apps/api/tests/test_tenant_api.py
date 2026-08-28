import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_authenticated_session, require_authenticated_actor
from app.api.routes.organizations import get_tenant_service, tenant_service
from app.api.tenant_errors import tenant_error_handler
from app.core.auth import AuthenticatedActor
from app.main import app
from app.tenants.errors import (
    LastOwnerRequiredError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    MembershipUserNotFoundError,
    OrganizationNotFoundError,
    TenantAuthorizationError,
    TenantError,
)
from app.tenants.models import Membership, Organization
from app.tenants.service import TenantService

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
ACTOR_USER_ID = UUID("10000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("30000000-0000-0000-0000-000000000001")


def _actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        user_id=ACTOR_USER_ID,
        email="person@example.com",
        expires_at=NOW + timedelta(minutes=5),
    )


def _organization() -> Organization:
    return Organization(
        id=ORGANIZATION_ID,
        name="Example Organization",
        role="owner",
        created_at=NOW,
        updated_at=NOW,
    )


def _membership() -> Membership:
    return Membership(
        id=MEMBERSHIP_ID,
        organization_id=ORGANIZATION_ID,
        user_id=ACTOR_USER_ID,
        display_name="Example Person",
        role="owner",
        created_at=NOW,
        updated_at=NOW,
    )


def test_organization_and_membership_http_contracts() -> None:
    service_mock = MagicMock(spec=TenantService)
    service_mock.list_organizations.return_value = [_organization()]
    service_mock.create_organization.return_value = _organization()
    service_mock.get_organization.return_value = _organization()
    service_mock.update_organization.return_value = _organization()
    service_mock.list_memberships.return_value = [_membership()]
    service_mock.create_membership.return_value = _membership()
    service_mock.update_membership.return_value = _membership()
    service_mock.delete_membership.return_value = None
    session = MagicMock(spec=AsyncSession)

    async def actor_override() -> AuthenticatedActor:
        return _actor()

    async def session_override() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, session)

    def service_override() -> TenantService:
        return cast(TenantService, service_mock)

    app.dependency_overrides[require_authenticated_actor] = actor_override
    app.dependency_overrides[get_authenticated_session] = session_override
    app.dependency_overrides[get_tenant_service] = service_override
    client = TestClient(app)
    try:
        list_response = client.get("/api/v1/organizations")
        create_response = client.post(
            "/api/v1/organizations", json={"name": "  Example Organization  "}
        )
        get_response = client.get(f"/api/v1/organizations/{ORGANIZATION_ID}")
        update_response = client.patch(
            f"/api/v1/organizations/{ORGANIZATION_ID}",
            json={"name": "Example Organization"},
        )
        memberships_response = client.get(f"/api/v1/organizations/{ORGANIZATION_ID}/memberships")
        membership_create_response = client.post(
            f"/api/v1/organizations/{ORGANIZATION_ID}/memberships",
            json={"user_id": str(ACTOR_USER_ID), "role": "owner"},
        )
        membership_update_response = client.patch(
            f"/api/v1/organizations/{ORGANIZATION_ID}/memberships/{MEMBERSHIP_ID}",
            json={"role": "owner"},
        )
        membership_delete_response = client.delete(
            f"/api/v1/organizations/{ORGANIZATION_ID}/memberships/{MEMBERSHIP_ID}"
        )
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == str(ORGANIZATION_ID)
    assert create_response.status_code == 201
    assert get_response.status_code == 200
    assert update_response.status_code == 200
    assert memberships_response.json()[0]["display_name"] == "Example Person"
    assert membership_create_response.status_code == 201
    assert membership_update_response.status_code == 200
    assert membership_delete_response.status_code == 204
    service_mock.create_organization.assert_awaited_once_with(
        session, ACTOR_USER_ID, "Example Organization"
    )


def test_default_tenant_service_is_configured() -> None:
    assert get_tenant_service() is tenant_service


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (OrganizationNotFoundError(), 404, "organization_not_found"),
        (MembershipNotFoundError(), 404, "membership_not_found"),
        (TenantAuthorizationError(), 403, "insufficient_role"),
        (MembershipAlreadyExistsError(), 409, "membership_already_exists"),
        (MembershipUserNotFoundError(), 404, "membership_user_not_found"),
        (LastOwnerRequiredError(), 409, "last_owner_required"),
    ],
)
def test_tenant_errors_use_stable_public_contract(
    error: TenantError, status_code: int, code: str
) -> None:
    request = Request({"type": "http", "headers": []})
    request.state.request_id = "request-id"

    response = asyncio.run(tenant_error_handler(request, error))

    assert response.status_code == status_code
    assert f'"code":"{code}"'.encode() in response.body


def test_tenant_error_handler_reraises_unexpected_exception() -> None:
    request = Request({"type": "http", "headers": []})

    with pytest.raises(RuntimeError, match="unexpected"):
        asyncio.run(tenant_error_handler(request, RuntimeError("unexpected")))


def test_tenant_error_handler_requires_explicit_mapping_for_new_domain_errors() -> None:
    request = Request({"type": "http", "headers": []})
    error = TenantError("new error")

    with pytest.raises(TenantError, match="new error"):
        asyncio.run(tenant_error_handler(request, error))
