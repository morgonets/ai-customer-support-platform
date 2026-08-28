import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.datastructures import State

from app.api.dependencies import get_authenticated_session
from app.core.auth import AuthenticatedActor
from app.core.database import Database, database_from_app_state


def _actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        user_id=uuid4(),
        email=None,
        expires_at=datetime.now(tz=UTC),
    )


def test_database_ping_dispose_and_authenticated_transaction() -> None:
    engine = MagicMock(spec=AsyncEngine)
    connection = AsyncMock()
    engine.connect.return_value.__aenter__.return_value = connection
    session = AsyncMock()
    session_factory = MagicMock()
    session_factory.begin.return_value.__aenter__.return_value = session

    with (
        patch("app.core.database.create_async_engine", return_value=engine),
        patch("app.core.database.async_sessionmaker", return_value=session_factory),
    ):
        database = Database("postgresql+psycopg://unused")

    asyncio.run(database.ping())
    asyncio.run(database.dispose())

    actor = _actor()

    async def use_session() -> None:
        async with database.session_for(actor) as yielded_session:
            assert yielded_session is session

    asyncio.run(use_session())

    connection.execute.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    assert session.execute.await_count == 2
    claims_parameters = session.execute.await_args_list[0].args[1]
    assert json.loads(claims_parameters["claims"]) == {
        "aud": "authenticated",
        "role": "authenticated",
        "sub": str(actor.user_id),
    }
    assert str(session.execute.await_args_list[1].args[0]) == "set local role app_api"


def test_database_from_application_state_fails_closed() -> None:
    state = State({"database": SimpleNamespace()})

    with pytest.raises(RuntimeError, match="not configured"):
        database_from_app_state(state)


def test_database_from_application_state_returns_database() -> None:
    database = Database.__new__(Database)
    state = State({"database": database})

    assert database_from_app_state(state) is database


def test_authenticated_session_dependency_yields_transaction_session() -> None:
    database = Database.__new__(Database)
    session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def session_for(actor: AuthenticatedActor) -> AsyncIterator[AsyncSession]:
        assert actor == _actor_value
        yield session

    _actor_value = _actor()
    database.session_for = session_for  # type: ignore[method-assign]

    async def exercise() -> None:
        sessions = [yielded async for yielded in get_authenticated_session(_actor_value, database)]
        assert sessions == [session]

    asyncio.run(exercise())
