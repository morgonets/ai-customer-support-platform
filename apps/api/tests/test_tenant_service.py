import asyncio
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenants.errors import (
    LastOwnerRequiredError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    MembershipUserNotFoundError,
    OrganizationNotFoundError,
    TenantAuthorizationError,
)
from app.tenants.models import Membership, Organization, OrganizationRole
from app.tenants.repository import TenantRepository
from app.tenants.service import TenantService

NOW = datetime(2026, 8, 28, tzinfo=UTC)
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
ACTOR_USER_ID = UUID("10000000-0000-0000-0000-000000000001")
ACTOR_MEMBERSHIP_ID = UUID("30000000-0000-0000-0000-000000000001")
TARGET_USER_ID = UUID("10000000-0000-0000-0000-000000000002")
TARGET_MEMBERSHIP_ID = UUID("30000000-0000-0000-0000-000000000002")
GENERATED_ID = UUID("40000000-0000-0000-0000-000000000001")


def _organization(role: OrganizationRole = "owner") -> Organization:
    return Organization(
        id=ORGANIZATION_ID,
        name="Example Organization",
        role=role,
        created_at=NOW,
        updated_at=NOW,
    )


def _membership(
    *,
    membership_id: UUID = TARGET_MEMBERSHIP_ID,
    user_id: UUID = TARGET_USER_ID,
    role: OrganizationRole = "member",
) -> Membership:
    return Membership(
        id=membership_id,
        organization_id=ORGANIZATION_ID,
        user_id=user_id,
        display_name=None,
        role=role,
        created_at=NOW,
        updated_at=NOW,
    )


def _repository() -> tuple[MagicMock, TenantRepository]:
    repository_mock = MagicMock(spec=TenantRepository)
    return repository_mock, cast(TenantRepository, repository_mock)


def _service_with_actor_role(
    role: OrganizationRole,
) -> tuple[TenantService, MagicMock, AsyncMock]:
    repository_mock, repository = _repository()
    repository_mock.get_membership.return_value = _membership(
        membership_id=ACTOR_MEMBERSHIP_ID,
        user_id=ACTOR_USER_ID,
        role=role,
    )
    service = TenantService(repository, id_factory=lambda: GENERATED_ID)
    return service, repository_mock, AsyncMock(spec=AsyncSession)


def _integrity_error(cause: Exception) -> IntegrityError:
    return IntegrityError("statement", {}, cause)


def test_service_lists_creates_and_gets_organizations() -> None:
    repository_mock, repository = _repository()
    repository_mock.list_organizations.return_value = [_organization()]
    repository_mock.create_organization.return_value = _organization()
    repository_mock.get_organization.side_effect = [_organization(), None]
    service = TenantService(repository, id_factory=lambda: GENERATED_ID)
    session = AsyncMock(spec=AsyncSession)

    async def exercise() -> None:
        listed = await service.list_organizations(session, ACTOR_USER_ID)
        created = await service.create_organization(session, ACTOR_USER_ID, "Example")
        found = await service.get_organization(session, ACTOR_USER_ID, ORGANIZATION_ID)
        assert listed == [_organization()]
        assert created == _organization()
        assert found == _organization()
        with pytest.raises(OrganizationNotFoundError):
            await service.get_organization(session, ACTOR_USER_ID, uuid4())

    asyncio.run(exercise())
    repository_mock.create_organization.assert_awaited_once_with(
        session, GENERATED_ID, ACTOR_USER_ID, "Example"
    )


def test_tenant_context_hides_organizations_without_membership() -> None:
    service, repository_mock, session = _service_with_actor_role("member")
    repository_mock.get_membership.return_value = None

    with pytest.raises(OrganizationNotFoundError):
        asyncio.run(service.list_memberships(session, ACTOR_USER_ID, ORGANIZATION_ID))


def test_owner_and_admin_update_organization_but_member_cannot() -> None:
    async def update_as(role: OrganizationRole) -> Organization:
        service, repository_mock, session = _service_with_actor_role(role)
        repository_mock.update_organization_name.return_value = _organization(role)
        return await service.update_organization(session, ACTOR_USER_ID, ORGANIZATION_ID, "Updated")

    assert asyncio.run(update_as("owner")).role == "owner"
    assert asyncio.run(update_as("admin")).role == "admin"
    with pytest.raises(TenantAuthorizationError):
        asyncio.run(update_as("member"))


def test_update_organization_handles_disappearing_row() -> None:
    service, repository_mock, session = _service_with_actor_role("owner")
    repository_mock.update_organization_name.return_value = None

    with pytest.raises(OrganizationNotFoundError):
        asyncio.run(service.update_organization(session, ACTOR_USER_ID, ORGANIZATION_ID, "Updated"))


def test_any_member_can_list_memberships() -> None:
    service, repository_mock, session = _service_with_actor_role("member")
    repository_mock.list_memberships.return_value = [_membership()]

    memberships = asyncio.run(service.list_memberships(session, ACTOR_USER_ID, ORGANIZATION_ID))

    assert memberships == [_membership()]


@pytest.mark.parametrize(
    ("actor_role", "new_role"),
    [("owner", "owner"), ("owner", "admin"), ("owner", "member"), ("admin", "member")],
)
def test_authorized_roles_can_create_memberships(
    actor_role: OrganizationRole, new_role: OrganizationRole
) -> None:
    service, repository_mock, session = _service_with_actor_role(actor_role)
    repository_mock.create_membership.return_value = _membership(role=new_role)

    membership = asyncio.run(
        service.create_membership(session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_USER_ID, new_role)
    )

    assert membership.role == new_role
    repository_mock.create_membership.assert_awaited_once_with(
        session, GENERATED_ID, ORGANIZATION_ID, TARGET_USER_ID, new_role
    )


@pytest.mark.parametrize(
    ("actor_role", "new_role"),
    [("member", "member"), ("admin", "admin"), ("admin", "owner")],
)
def test_unauthorized_roles_cannot_create_memberships(
    actor_role: OrganizationRole, new_role: OrganizationRole
) -> None:
    service, _, session = _service_with_actor_role(actor_role)

    with pytest.raises(TenantAuthorizationError):
        asyncio.run(
            service.create_membership(
                session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_USER_ID, new_role
            )
        )


@pytest.mark.parametrize(
    ("cause", "expected"),
    [
        (UniqueViolation("duplicate"), MembershipAlreadyExistsError),
        (ForeignKeyViolation("missing"), MembershipUserNotFoundError),
    ],
)
def test_create_membership_maps_expected_database_conflicts(
    cause: Exception, expected: type[Exception]
) -> None:
    service, repository_mock, session = _service_with_actor_role("owner")
    repository_mock.create_membership.side_effect = _integrity_error(cause)

    with pytest.raises(expected):
        asyncio.run(
            service.create_membership(
                session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_USER_ID, "member"
            )
        )


def test_create_membership_reraises_unexpected_database_failure() -> None:
    service, repository_mock, session = _service_with_actor_role("owner")
    error = _integrity_error(RuntimeError("unexpected"))
    repository_mock.create_membership.side_effect = error

    with pytest.raises(IntegrityError) as raised:
        asyncio.run(
            service.create_membership(
                session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_USER_ID, "member"
            )
        )
    assert raised.value is error


def test_only_owner_can_update_membership_role() -> None:
    service, repository_mock, session = _service_with_actor_role("owner")
    repository_mock.get_membership_by_id.return_value = _membership()
    repository_mock.update_membership_role.return_value = _membership(role="admin")

    updated = asyncio.run(
        service.update_membership(
            session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID, "admin"
        )
    )
    assert updated.role == "admin"

    for role in ("admin", "member"):
        denied_service, _, denied_session = _service_with_actor_role(role)
        with pytest.raises(TenantAuthorizationError):
            asyncio.run(
                denied_service.update_membership(
                    denied_session,
                    ACTOR_USER_ID,
                    ORGANIZATION_ID,
                    TARGET_MEMBERSHIP_ID,
                    "admin",
                )
            )


def test_update_membership_handles_missing_and_last_owner_invariants() -> None:
    service, repository_mock, session = _service_with_actor_role("owner")
    repository_mock.get_membership_by_id.side_effect = [_membership(), None, _membership()]
    repository_mock.update_membership_role.side_effect = [
        None,
        _integrity_error(CheckViolation("last owner")),
    ]

    with pytest.raises(MembershipNotFoundError):
        asyncio.run(
            service.update_membership(
                session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID, "member"
            )
        )
    with pytest.raises(MembershipNotFoundError):
        asyncio.run(
            service.update_membership(
                session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID, "member"
            )
        )
    with pytest.raises(LastOwnerRequiredError):
        asyncio.run(
            service.update_membership(
                session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID, "member"
            )
        )


def test_update_membership_reraises_unexpected_database_failure() -> None:
    service, repository_mock, session = _service_with_actor_role("owner")
    repository_mock.get_membership_by_id.return_value = _membership()
    error = _integrity_error(RuntimeError("unexpected"))
    repository_mock.update_membership_role.side_effect = error

    with pytest.raises(IntegrityError) as raised:
        asyncio.run(
            service.update_membership(
                session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID, "member"
            )
        )
    assert raised.value is error


@pytest.mark.parametrize(
    ("actor_role", "target_user_id", "target_role"),
    [
        ("member", ACTOR_USER_ID, "member"),
        ("owner", TARGET_USER_ID, "owner"),
        ("admin", TARGET_USER_ID, "member"),
    ],
)
def test_authorized_members_can_remove_membership(
    actor_role: OrganizationRole, target_user_id: UUID, target_role: OrganizationRole
) -> None:
    service, repository_mock, session = _service_with_actor_role(actor_role)
    repository_mock.get_membership_by_id.return_value = _membership(
        user_id=target_user_id, role=target_role
    )
    repository_mock.delete_membership.return_value = True

    asyncio.run(
        service.delete_membership(session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID)
    )

    repository_mock.delete_membership.assert_awaited_once()


@pytest.mark.parametrize(
    ("actor_role", "target_role"), [("member", "member"), ("admin", "admin"), ("admin", "owner")]
)
def test_unauthorized_members_cannot_remove_others(
    actor_role: OrganizationRole, target_role: OrganizationRole
) -> None:
    service, repository_mock, session = _service_with_actor_role(actor_role)
    repository_mock.get_membership_by_id.return_value = _membership(role=target_role)

    with pytest.raises(TenantAuthorizationError):
        asyncio.run(
            service.delete_membership(session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID)
        )


def test_delete_membership_handles_last_owner_missing_and_unexpected_failures() -> None:
    service, repository_mock, session = _service_with_actor_role("owner")
    repository_mock.get_membership_by_id.return_value = _membership(role="owner")
    repository_mock.delete_membership.side_effect = [
        _integrity_error(CheckViolation("last owner")),
        False,
        _integrity_error(RuntimeError("unexpected")),
    ]

    with pytest.raises(LastOwnerRequiredError):
        asyncio.run(
            service.delete_membership(session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID)
        )
    with pytest.raises(MembershipNotFoundError):
        asyncio.run(
            service.delete_membership(session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID)
        )
    with pytest.raises(IntegrityError):
        asyncio.run(
            service.delete_membership(session, ACTOR_USER_ID, ORGANIZATION_ID, TARGET_MEMBERSHIP_ID)
        )
