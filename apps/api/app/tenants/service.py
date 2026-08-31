from collections.abc import Callable, Sequence
from uuid import UUID, uuid4

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenants.authorization import TenantAuthorizer
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


class TenantService:
    def __init__(
        self, repository: TenantRepository, id_factory: Callable[[], UUID] = uuid4
    ) -> None:
        self._repository = repository
        self._authorizer = TenantAuthorizer(repository)
        self._id_factory = id_factory

    async def list_organizations(
        self, session: AsyncSession, actor_user_id: UUID
    ) -> Sequence[Organization]:
        return await self._repository.list_organizations(session, actor_user_id)

    async def create_organization(
        self, session: AsyncSession, actor_user_id: UUID, name: str
    ) -> Organization:
        return await self._repository.create_organization(
            session, self._id_factory(), actor_user_id, name
        )

    async def get_organization(
        self, session: AsyncSession, actor_user_id: UUID, organization_id: UUID
    ) -> Organization:
        organization = await self._repository.get_organization(
            session, organization_id, actor_user_id
        )
        if organization is None:
            raise OrganizationNotFoundError
        return organization

    async def update_organization(
        self, session: AsyncSession, actor_user_id: UUID, organization_id: UUID, name: str
    ) -> Organization:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        organization = await self._repository.update_organization_name(
            session, organization_id, actor_user_id, name
        )
        if organization is None:
            raise OrganizationNotFoundError
        return organization

    async def list_memberships(
        self, session: AsyncSession, actor_user_id: UUID, organization_id: UUID
    ) -> Sequence[Membership]:
        await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        return await self._repository.list_memberships(session, organization_id)

    async def create_membership(
        self,
        session: AsyncSession,
        actor_user_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        role: OrganizationRole,
    ) -> Membership:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        if context.role == "member" or (context.role == "admin" and role != "member"):
            raise TenantAuthorizationError
        try:
            return await self._repository.create_membership(
                session, self._id_factory(), organization_id, user_id, role
            )
        except IntegrityError as exc:
            if isinstance(exc.orig, UniqueViolation):
                raise MembershipAlreadyExistsError from exc
            if isinstance(exc.orig, ForeignKeyViolation):
                raise MembershipUserNotFoundError from exc
            raise

    async def update_membership(
        self,
        session: AsyncSession,
        actor_user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
        role: OrganizationRole,
    ) -> Membership:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner")
        await self._target_membership(session, organization_id, membership_id)
        try:
            membership = await self._repository.update_membership_role(
                session, organization_id, membership_id, role
            )
        except IntegrityError as exc:
            if isinstance(exc.orig, CheckViolation):
                raise LastOwnerRequiredError from exc
            raise
        if membership is None:
            raise MembershipNotFoundError
        return membership

    async def delete_membership(
        self,
        session: AsyncSession,
        actor_user_id: UUID,
        organization_id: UUID,
        membership_id: UUID,
    ) -> None:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        target = await self._target_membership(session, organization_id, membership_id)
        is_self = target.user_id == actor_user_id
        may_remove = (
            is_self
            or context.role == "owner"
            or (context.role == "admin" and target.role == "member")
        )
        if not may_remove:
            raise TenantAuthorizationError
        try:
            deleted = await self._repository.delete_membership(
                session, organization_id, membership_id
            )
        except IntegrityError as exc:
            if isinstance(exc.orig, CheckViolation):
                raise LastOwnerRequiredError from exc
            raise
        if not deleted:
            raise MembershipNotFoundError

    async def _target_membership(
        self, session: AsyncSession, organization_id: UUID, membership_id: UUID
    ) -> Membership:
        membership = await self._repository.get_membership_by_id(
            session, organization_id, membership_id
        )
        if membership is None:
            raise MembershipNotFoundError
        return membership
