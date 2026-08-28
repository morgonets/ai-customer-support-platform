from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.tenants.models import Membership, Organization, OrganizationRole


class TenantRepository(Protocol):
    async def list_organizations(
        self, session: AsyncSession, actor_user_id: UUID
    ) -> Sequence[Organization]: ...

    async def create_organization(
        self, session: AsyncSession, organization_id: UUID, actor_user_id: UUID, name: str
    ) -> Organization: ...

    async def get_organization(
        self, session: AsyncSession, organization_id: UUID, actor_user_id: UUID
    ) -> Organization | None: ...

    async def update_organization_name(
        self, session: AsyncSession, organization_id: UUID, actor_user_id: UUID, name: str
    ) -> Organization | None: ...

    async def get_membership(
        self, session: AsyncSession, organization_id: UUID, user_id: UUID
    ) -> Membership | None: ...

    async def get_membership_by_id(
        self, session: AsyncSession, organization_id: UUID, membership_id: UUID
    ) -> Membership | None: ...

    async def list_memberships(
        self, session: AsyncSession, organization_id: UUID
    ) -> Sequence[Membership]: ...

    async def create_membership(
        self,
        session: AsyncSession,
        membership_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        role: OrganizationRole,
    ) -> Membership: ...

    async def update_membership_role(
        self,
        session: AsyncSession,
        organization_id: UUID,
        membership_id: UUID,
        role: OrganizationRole,
    ) -> Membership | None: ...

    async def delete_membership(
        self, session: AsyncSession, organization_id: UUID, membership_id: UUID
    ) -> bool: ...


class SqlAlchemyTenantRepository:
    async def list_organizations(
        self, session: AsyncSession, actor_user_id: UUID
    ) -> Sequence[Organization]:
        result = await session.execute(
            text(
                """
                select organization.id, organization.name, membership.role,
                       organization.created_at, organization.updated_at
                from app.organizations as organization
                inner join app.organization_memberships as membership
                  on membership.organization_id = organization.id
                where membership.user_id = :actor_user_id
                order by organization.created_at, organization.id
                """
            ),
            {"actor_user_id": actor_user_id},
        )
        return [self._organization(row) for row in result.mappings().all()]

    async def create_organization(
        self, session: AsyncSession, organization_id: UUID, actor_user_id: UUID, name: str
    ) -> Organization:
        await session.execute(
            text(
                """
                insert into app.organizations (id, name, created_by_user_id)
                values (:organization_id, :name, :actor_user_id)
                """
            ),
            {
                "organization_id": organization_id,
                "name": name,
                "actor_user_id": actor_user_id,
            },
        )
        await session.execute(
            text(
                """
                insert into app.organization_memberships
                  (organization_id, user_id, role)
                values (:organization_id, :actor_user_id, 'owner')
                """
            ),
            {"organization_id": organization_id, "actor_user_id": actor_user_id},
        )
        organization = await self.get_organization(session, organization_id, actor_user_id)
        if organization is None:
            raise RuntimeError("created organization is not visible to its owner")
        return organization

    async def get_organization(
        self, session: AsyncSession, organization_id: UUID, actor_user_id: UUID
    ) -> Organization | None:
        result = await session.execute(
            text(
                """
                select organization.id, organization.name, membership.role,
                       organization.created_at, organization.updated_at
                from app.organizations as organization
                inner join app.organization_memberships as membership
                  on membership.organization_id = organization.id
                where organization.id = :organization_id
                  and membership.user_id = :actor_user_id
                """
            ),
            {"organization_id": organization_id, "actor_user_id": actor_user_id},
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._organization(row)

    async def update_organization_name(
        self, session: AsyncSession, organization_id: UUID, actor_user_id: UUID, name: str
    ) -> Organization | None:
        result = await session.execute(
            text(
                """
                update app.organizations as organization
                set name = :name
                from app.organization_memberships as membership
                where organization.id = :organization_id
                  and membership.organization_id = organization.id
                  and membership.user_id = :actor_user_id
                returning organization.id, organization.name, membership.role,
                          organization.created_at, organization.updated_at
                """
            ),
            {
                "organization_id": organization_id,
                "actor_user_id": actor_user_id,
                "name": name,
            },
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._organization(row)

    async def get_membership(
        self, session: AsyncSession, organization_id: UUID, user_id: UUID
    ) -> Membership | None:
        result = await session.execute(
            self._membership_select(
                "membership.organization_id = :organization_id and membership.user_id = :user_id"
            ),
            {"organization_id": organization_id, "user_id": user_id},
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._membership(row)

    async def get_membership_by_id(
        self, session: AsyncSession, organization_id: UUID, membership_id: UUID
    ) -> Membership | None:
        result = await session.execute(
            self._membership_select(
                "membership.organization_id = :organization_id and membership.id = :membership_id"
            ),
            {"organization_id": organization_id, "membership_id": membership_id},
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._membership(row)

    async def list_memberships(
        self, session: AsyncSession, organization_id: UUID
    ) -> Sequence[Membership]:
        result = await session.execute(
            self._membership_select(
                "membership.organization_id = :organization_id "
                "order by membership.created_at, membership.id"
            ),
            {"organization_id": organization_id},
        )
        return [self._membership(row) for row in result.mappings().all()]

    async def create_membership(
        self,
        session: AsyncSession,
        membership_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        role: OrganizationRole,
    ) -> Membership:
        result = await session.execute(
            text(
                """
                insert into app.organization_memberships
                  (id, organization_id, user_id, role)
                values (:membership_id, :organization_id, :user_id, :role)
                returning id, organization_id, user_id, role, created_at, updated_at,
                          null::text as display_name
                """
            ),
            {
                "membership_id": membership_id,
                "organization_id": organization_id,
                "user_id": user_id,
                "role": role,
            },
        )
        return self._membership(result.mappings().one())

    async def update_membership_role(
        self,
        session: AsyncSession,
        organization_id: UUID,
        membership_id: UUID,
        role: OrganizationRole,
    ) -> Membership | None:
        result = await session.execute(
            text(
                """
                update app.organization_memberships as membership
                set role = :role
                where membership.organization_id = :organization_id
                  and membership.id = :membership_id
                returning membership.id, membership.organization_id, membership.user_id,
                          membership.role, membership.created_at, membership.updated_at,
                          null::text as display_name
                """
            ),
            {
                "organization_id": organization_id,
                "membership_id": membership_id,
                "role": role,
            },
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._membership(row)

    async def delete_membership(
        self, session: AsyncSession, organization_id: UUID, membership_id: UUID
    ) -> bool:
        result = await session.execute(
            text(
                """
                delete from app.organization_memberships
                where organization_id = :organization_id and id = :membership_id
                """
            ),
            {"organization_id": organization_id, "membership_id": membership_id},
        )
        cursor_result = cast(CursorResult[tuple[object, ...]], result)
        return bool(cursor_result.rowcount)

    @staticmethod
    def _membership_select(predicate: str) -> TextClause:
        return text(
            f"""
            select membership.id, membership.organization_id, membership.user_id,
                   profile.display_name, membership.role, membership.created_at,
                   membership.updated_at
            from app.organization_memberships as membership
            inner join app.user_profiles as profile on profile.user_id = membership.user_id
            where {predicate}
            """  # noqa: S608 -- predicate is a private static SQL fragment, never caller input.
        )

    @staticmethod
    def _organization(row: RowMapping, role: OrganizationRole | None = None) -> Organization:
        return Organization(
            id=cast(UUID, row["id"]),
            name=cast(str, row["name"]),
            role=role or cast(OrganizationRole, row["role"]),
            created_at=cast(datetime, row["created_at"]),
            updated_at=cast(datetime, row["updated_at"]),
        )

    @staticmethod
    def _membership(row: RowMapping) -> Membership:
        return Membership(
            id=cast(UUID, row["id"]),
            organization_id=cast(UUID, row["organization_id"]),
            user_id=cast(UUID, row["user_id"]),
            display_name=cast(str | None, row["display_name"]),
            role=cast(OrganizationRole, row["role"]),
            created_at=cast(datetime, row["created_at"]),
            updated_at=cast(datetime, row["updated_at"]),
        )
