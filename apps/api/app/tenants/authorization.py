from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.tenants.errors import OrganizationNotFoundError, TenantAuthorizationError
from app.tenants.models import OrganizationRole, TenantContext
from app.tenants.repository import TenantRepository


class TenantAuthorizer:
    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    async def require_context(
        self, session: AsyncSession, *, actor_user_id: UUID, organization_id: UUID
    ) -> TenantContext:
        membership = await self._repository.get_membership(session, organization_id, actor_user_id)
        if membership is None:
            raise OrganizationNotFoundError
        return TenantContext(
            organization_id=organization_id,
            actor_membership_id=membership.id,
            actor_user_id=actor_user_id,
            role=membership.role,
        )

    @staticmethod
    def require_role(context: TenantContext, *allowed_roles: OrganizationRole) -> None:
        if context.role not in allowed_roles:
            raise TenantAuthorizationError
