from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.dependencies import CurrentActor, CurrentSession
from app.tenants.models import Membership, Organization, OrganizationRole
from app.tenants.repository import SqlAlchemyTenantRepository
from app.tenants.service import TenantService

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])
OrganizationName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]

tenant_service = TenantService(SqlAlchemyTenantRepository())


def get_tenant_service() -> TenantService:
    return tenant_service


TenantServiceDependency = Annotated[TenantService, Depends(get_tenant_service)]


class OrganizationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: OrganizationName


class OrganizationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: OrganizationName


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    role: OrganizationRole
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, organization: Organization) -> "OrganizationResponse":
        return cls(
            id=organization.id,
            name=organization.name,
            role=organization.role,
            created_at=organization.created_at,
            updated_at=organization.updated_at,
        )


class MembershipCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: OrganizationRole = "member"


class MembershipUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: OrganizationRole


class MembershipResponse(BaseModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    display_name: str | None
    role: OrganizationRole
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, membership: Membership) -> "MembershipResponse":
        return cls(
            id=membership.id,
            organization_id=membership.organization_id,
            user_id=membership.user_id,
            display_name=membership.display_name,
            role=membership.role,
            created_at=membership.created_at,
            updated_at=membership.updated_at,
        )


@router.get("", response_model=list[OrganizationResponse], summary="List organizations")
async def list_organizations(
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> list[OrganizationResponse]:
    organizations = await service.list_organizations(session, actor.user_id)
    return [OrganizationResponse.from_domain(organization) for organization in organizations]


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an organization",
)
async def create_organization(
    body: OrganizationCreateRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> OrganizationResponse:
    organization = await service.create_organization(session, actor.user_id, body.name)
    return OrganizationResponse.from_domain(organization)


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
    summary="Get an organization",
)
async def get_organization(
    organization_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> OrganizationResponse:
    organization = await service.get_organization(session, actor.user_id, organization_id)
    return OrganizationResponse.from_domain(organization)


@router.patch(
    "/{organization_id}",
    response_model=OrganizationResponse,
    summary="Update an organization",
)
async def update_organization(
    organization_id: UUID,
    body: OrganizationUpdateRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> OrganizationResponse:
    organization = await service.update_organization(
        session, actor.user_id, organization_id, body.name
    )
    return OrganizationResponse.from_domain(organization)


@router.get(
    "/{organization_id}/memberships",
    response_model=list[MembershipResponse],
    summary="List organization memberships",
)
async def list_memberships(
    organization_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> list[MembershipResponse]:
    memberships = await service.list_memberships(session, actor.user_id, organization_id)
    return [MembershipResponse.from_domain(membership) for membership in memberships]


@router.post(
    "/{organization_id}/memberships",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an existing user to an organization",
)
async def create_membership(
    organization_id: UUID,
    body: MembershipCreateRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> MembershipResponse:
    membership = await service.create_membership(
        session, actor.user_id, organization_id, body.user_id, body.role
    )
    return MembershipResponse.from_domain(membership)


@router.patch(
    "/{organization_id}/memberships/{membership_id}",
    response_model=MembershipResponse,
    summary="Change a membership role",
)
async def update_membership(
    organization_id: UUID,
    membership_id: UUID,
    body: MembershipUpdateRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> MembershipResponse:
    membership = await service.update_membership(
        session, actor.user_id, organization_id, membership_id, body.role
    )
    return MembershipResponse.from_domain(membership)


@router.delete(
    "/{organization_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an organization membership",
)
async def delete_membership(
    organization_id: UUID,
    membership_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: TenantServiceDependency,
) -> Response:
    await service.delete_membership(session, actor.user_id, organization_id, membership_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
