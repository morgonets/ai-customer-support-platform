import asyncio
import json
import os
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.tenants.errors import OrganizationNotFoundError, TenantAuthorizationError
from app.tenants.repository import SqlAlchemyTenantRepository
from app.tenants.service import TenantService

ADMIN_DATABASE_URL = os.getenv("INTEGRATION_DATABASE_ADMIN_URL")
OWNER_ID = UUID("11000000-0000-0000-0000-000000000001")
ADMIN_ID = UUID("11000000-0000-0000-0000-000000000002")
MEMBER_ID = UUID("11000000-0000-0000-0000-000000000003")
OUTSIDER_ID = UUID("11000000-0000-0000-0000-000000000004")
ORGANIZATION_ID = UUID("22000000-0000-0000-0000-000000000001")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        ADMIN_DATABASE_URL is None,
        reason="INTEGRATION_DATABASE_ADMIN_URL is required for persistence integration tests",
    ),
]


async def _assume_actor(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(text("reset role"))
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"}, separators=(",", ":"))
    await session.execute(
        text("select set_config('request.jwt.claims', :claims, true)"), {"claims": claims}
    )
    await session.execute(text("set local role app_api"))


async def _exercise_persistence() -> None:
    assert ADMIN_DATABASE_URL is not None
    engine = create_async_engine(ADMIN_DATABASE_URL)
    session = AsyncSession(engine, expire_on_commit=False)
    transaction = await session.begin()
    repository = SqlAlchemyTenantRepository()
    generated_ids = iter(
        [
            ORGANIZATION_ID,
            UUID("33000000-0000-0000-0000-000000000001"),
            UUID("33000000-0000-0000-0000-000000000002"),
        ]
    )
    service = TenantService(repository, id_factory=lambda: next(generated_ids))
    try:
        await session.execute(
            text(
                """
                insert into auth.users (
                  id, email, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
                )
                values
                  (:owner_id, 'integration-owner@example.test', '{}', '{}', now(), now()),
                  (:admin_id, 'integration-admin@example.test', '{}', '{}', now(), now()),
                  (:member_id, 'integration-member@example.test', '{}', '{}', now(), now()),
                  (:outsider_id, 'integration-outsider@example.test', '{}', '{}', now(), now())
                """
            ),
            {
                "owner_id": OWNER_ID,
                "admin_id": ADMIN_ID,
                "member_id": MEMBER_ID,
                "outsider_id": OUTSIDER_ID,
            },
        )

        await _assume_actor(session, OWNER_ID)
        organization = await service.create_organization(
            session, OWNER_ID, "Integration Organization"
        )
        assert organization.id == ORGANIZATION_ID
        await service.create_membership(session, OWNER_ID, ORGANIZATION_ID, ADMIN_ID, "admin")
        await service.create_membership(session, OWNER_ID, ORGANIZATION_ID, MEMBER_ID, "member")

        await _assume_actor(session, ADMIN_ID)
        updated = await service.update_organization(
            session, ADMIN_ID, ORGANIZATION_ID, "Updated Integration Organization"
        )
        assert updated.role == "admin"

        await _assume_actor(session, MEMBER_ID)
        assert len(await service.list_memberships(session, MEMBER_ID, ORGANIZATION_ID)) == 3
        with pytest.raises(TenantAuthorizationError):
            await service.update_organization(
                session, MEMBER_ID, ORGANIZATION_ID, "Forbidden Update"
            )

        await _assume_actor(session, OUTSIDER_ID)
        assert await service.list_organizations(session, OUTSIDER_ID) == []
        with pytest.raises(OrganizationNotFoundError):
            await service.get_organization(session, OUTSIDER_ID, ORGANIZATION_ID)
    finally:
        await transaction.rollback()
        await session.close()
        await engine.dispose()


def test_repository_and_service_enforce_tenant_boundary_in_postgresql() -> None:
    asyncio.run(_exercise_persistence())
