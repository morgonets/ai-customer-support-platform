import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tenants.repository import SqlAlchemyTenantRepository

NOW = datetime(2026, 8, 28, tzinfo=UTC)


class FakeResult:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]] | None = None,
        row: dict[str, object] | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows or []
        self._row = row
        self.rowcount = rowcount

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows

    def one(self) -> dict[str, object]:
        assert self._row is not None
        return self._row

    def one_or_none(self) -> dict[str, object] | None:
        return self._row


def _organization_row(organization_id: UUID, role: str = "owner") -> dict[str, object]:
    return {
        "id": organization_id,
        "name": "Example Organization",
        "role": role,
        "created_at": NOW,
        "updated_at": NOW,
    }


def _membership_row(membership_id: UUID, organization_id: UUID, user_id: UUID) -> dict[str, object]:
    return {
        "id": membership_id,
        "organization_id": organization_id,
        "user_id": user_id,
        "display_name": "Example Person",
        "role": "member",
        "created_at": NOW,
        "updated_at": NOW,
    }


def _session(*results: FakeResult) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = list(results)
    return session


def test_repository_lists_and_creates_organizations() -> None:
    repository = SqlAlchemyTenantRepository()
    organization_id = uuid4()
    actor_user_id = uuid4()
    session = _session(
        FakeResult(rows=[_organization_row(organization_id, "admin")]),
        FakeResult(),
        FakeResult(),
        FakeResult(row=_organization_row(organization_id)),
    )

    async def exercise() -> None:
        organizations = await repository.list_organizations(session, actor_user_id)
        created = await repository.create_organization(
            session, organization_id, actor_user_id, "Example Organization"
        )
        assert organizations[0].role == "admin"
        assert created.id == organization_id
        assert created.role == "owner"

    asyncio.run(exercise())
    assert session.execute.await_count == 4


def test_repository_create_organization_fails_if_bootstrapped_owner_cannot_read_it() -> None:
    repository = SqlAlchemyTenantRepository()
    session = _session(FakeResult(), FakeResult(), FakeResult())

    with pytest.raises(RuntimeError, match="not visible"):
        asyncio.run(
            repository.create_organization(session, uuid4(), uuid4(), "Example Organization")
        )


def test_repository_gets_and_updates_organization_with_not_found_results() -> None:
    repository = SqlAlchemyTenantRepository()
    organization_id = uuid4()
    actor_user_id = uuid4()
    session = _session(
        FakeResult(row=_organization_row(organization_id)),
        FakeResult(),
        FakeResult(row=_organization_row(organization_id, "admin")),
        FakeResult(),
    )

    async def exercise() -> None:
        found = await repository.get_organization(session, organization_id, actor_user_id)
        missing = await repository.get_organization(session, uuid4(), actor_user_id)
        updated = await repository.update_organization_name(
            session, organization_id, actor_user_id, "Updated"
        )
        update_missing = await repository.update_organization_name(
            session, uuid4(), actor_user_id, "Updated"
        )
        assert found is not None and found.name == "Example Organization"
        assert missing is None
        assert updated is not None and updated.role == "admin"
        assert update_missing is None

    asyncio.run(exercise())


def test_repository_reads_memberships_and_missing_results() -> None:
    repository = SqlAlchemyTenantRepository()
    organization_id = uuid4()
    membership_id = uuid4()
    user_id = uuid4()
    row = _membership_row(membership_id, organization_id, user_id)
    session = _session(
        FakeResult(row=row),
        FakeResult(),
        FakeResult(row=row),
        FakeResult(),
        FakeResult(rows=[row]),
    )

    async def exercise() -> None:
        by_user = await repository.get_membership(session, organization_id, user_id)
        missing_user = await repository.get_membership(session, organization_id, uuid4())
        by_id = await repository.get_membership_by_id(session, organization_id, membership_id)
        missing_id = await repository.get_membership_by_id(session, organization_id, uuid4())
        memberships = await repository.list_memberships(session, organization_id)
        assert by_user is not None and by_user.display_name == "Example Person"
        assert missing_user is None
        assert by_id is not None and by_id.id == membership_id
        assert missing_id is None
        assert memberships == [by_user]

    asyncio.run(exercise())


def test_repository_mutates_memberships_and_scopes_every_operation() -> None:
    repository = SqlAlchemyTenantRepository()
    organization_id = uuid4()
    membership_id = uuid4()
    user_id = uuid4()
    row = _membership_row(membership_id, organization_id, user_id)
    session = _session(
        FakeResult(row=row),
        FakeResult(row=row),
        FakeResult(),
        FakeResult(rowcount=1),
        FakeResult(rowcount=0),
    )

    async def exercise() -> None:
        created = await repository.create_membership(
            session, membership_id, organization_id, user_id, "member"
        )
        updated = await repository.update_membership_role(
            session, organization_id, membership_id, "admin"
        )
        missing = await repository.update_membership_role(
            session, organization_id, uuid4(), "admin"
        )
        deleted = await repository.delete_membership(session, organization_id, membership_id)
        not_deleted = await repository.delete_membership(session, organization_id, uuid4())
        assert created.user_id == user_id
        assert updated is not None
        assert missing is None
        assert deleted is True
        assert not_deleted is False

    asyncio.run(exercise())
    for call in session.execute.await_args_list:
        parameters = call.args[1]
        assert parameters.get("organization_id") == organization_id
