import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenants.authorization import TenantAuthorizer
from app.tenants.errors import OrganizationNotFoundError, TenantAuthorizationError
from app.tenants.models import Membership, OrganizationRole
from app.tenants.repository import TenantRepository

ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("30000000-0000-0000-0000-000000000001")


def _membership(role: OrganizationRole) -> Membership:
    from datetime import UTC, datetime

    now = datetime(2026, 8, 31, tzinfo=UTC)
    return Membership(
        id=MEMBERSHIP_ID,
        organization_id=ORGANIZATION_ID,
        user_id=ACTOR_ID,
        display_name=None,
        role=role,
        created_at=now,
        updated_at=now,
    )


def test_authorizer_resolves_context_and_checks_roles() -> None:
    repository_mock = MagicMock(spec=TenantRepository)
    repository_mock.get_membership.return_value = _membership("admin")
    authorizer = TenantAuthorizer(cast(TenantRepository, repository_mock))
    session = AsyncMock(spec=AsyncSession)

    context = asyncio.run(
        authorizer.require_context(session, actor_user_id=ACTOR_ID, organization_id=ORGANIZATION_ID)
    )

    assert context.role == "admin"
    authorizer.require_role(context, "owner", "admin")
    with pytest.raises(TenantAuthorizationError):
        authorizer.require_role(context, "owner")


def test_authorizer_hides_missing_or_foreign_organization() -> None:
    repository_mock = MagicMock(spec=TenantRepository)
    repository_mock.get_membership.return_value = None
    authorizer = TenantAuthorizer(cast(TenantRepository, repository_mock))

    with pytest.raises(OrganizationNotFoundError):
        asyncio.run(
            authorizer.require_context(
                AsyncMock(spec=AsyncSession),
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
            )
        )
