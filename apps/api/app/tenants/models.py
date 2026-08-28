from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

OrganizationRole = Literal["owner", "admin", "member"]


@dataclass(frozen=True, slots=True)
class Organization:
    id: UUID
    name: str
    role: OrganizationRole
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Membership:
    id: UUID
    organization_id: UUID
    user_id: UUID
    display_name: str | None
    role: OrganizationRole
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TenantContext:
    organization_id: UUID
    actor_membership_id: UUID
    actor_user_id: UUID
    role: OrganizationRole
