import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.datastructures import State

from app.core.auth import AuthenticatedActor


class Database:
    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(url, pool_pre_ping=True)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    async def ping(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("select 1"))

    async def dispose(self) -> None:
        await self._engine.dispose()

    @asynccontextmanager
    async def session_for(self, actor: AuthenticatedActor) -> AsyncIterator[AsyncSession]:
        trusted_claims = json.dumps(
            {
                "aud": "authenticated",
                "role": "authenticated",
                "sub": str(actor.user_id),
            },
            separators=(",", ":"),
        )
        async with self._sessions.begin() as session:
            await session.execute(
                text("select set_config('request.jwt.claims', :claims, true)"),
                {"claims": trusted_claims},
            )
            await session.execute(text("set local role app_api"))
            yield session


def database_from_app_state(state: State) -> Database:
    database = state.database
    if not isinstance(database, Database):
        raise RuntimeError("application database is not configured")
    return database
