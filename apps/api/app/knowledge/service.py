import base64
import binascii
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import (
    InvalidKnowledgeCursorError,
    KnowledgeContentUnavailableError,
    KnowledgeSourceKindError,
    KnowledgeSourceNotFoundError,
)
from app.knowledge.models import (
    KnowledgeProcessingStatus,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourcePage,
)
from app.knowledge.normalization import article_locator_map, normalize_text
from app.knowledge.repository import KnowledgeRepository
from app.tenants.authorization import TenantAuthorizer


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        authorizer: TenantAuthorizer,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._id_factory = id_factory
        self._clock = clock

    async def list_sources(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        limit: int,
        cursor: str | None,
        kind: KnowledgeSourceKind | None,
        status: KnowledgeProcessingStatus | None,
    ) -> KnowledgeSourcePage:
        await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        decoded_cursor = None if cursor is None else self._decode_cursor(cursor)
        rows = list(
            await self._repository.list_sources(
                session,
                organization_id,
                limit=limit + 1,
                cursor=decoded_cursor,
                kind=kind,
                status=status,
            )
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = self._encode_cursor(items[-1]) if has_more and items else None
        return KnowledgeSourcePage(items=items, next_cursor=next_cursor)

    async def get_source(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> KnowledgeSource:
        await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        return await self._required_source(session, organization_id, source_id)

    async def create_article(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        title: str,
        description: str | None,
        raw_text: str,
    ) -> KnowledgeSource:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        normalized_text = normalize_text(raw_text)
        return await self._repository.create_article(
            session,
            source_id=self._id_factory(),
            version_id=self._id_factory(),
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            title=title,
            description=description,
            raw_text=raw_text,
            normalized_text=normalized_text,
            locator_map=article_locator_map(normalized_text),
            processed_at=self._clock(),
        )

    async def update_metadata(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        title: str | None,
        description: str | None,
        description_is_set: bool,
    ) -> KnowledgeSource:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        current = await self._required_source(session, organization_id, source_id)
        source = await self._repository.update_metadata(
            session,
            organization_id=organization_id,
            source_id=source_id,
            actor_user_id=actor_user_id,
            title=current.title if title is None else title,
            description=description if description_is_set else current.description,
        )
        if source is None:
            raise KnowledgeSourceNotFoundError
        return source

    async def replace_article_content(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        raw_text: str,
    ) -> KnowledgeSource:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        current = await self._required_source(session, organization_id, source_id)
        if current.kind != "article":
            raise KnowledgeSourceKindError
        normalized_text = normalize_text(raw_text)
        source = await self._repository.replace_article_content(
            session,
            organization_id=organization_id,
            source_id=source_id,
            version_id=self._id_factory(),
            actor_user_id=actor_user_id,
            raw_text=raw_text,
            normalized_text=normalized_text,
            locator_map=article_locator_map(normalized_text),
            processed_at=self._clock(),
        )
        if source is None:
            raise KnowledgeSourceNotFoundError
        return source

    async def get_content(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> KnowledgeSource:
        source = await self.get_source(
            session,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            source_id=source_id,
        )
        if source.current_version.status != "ready":
            raise KnowledgeContentUnavailableError
        return source

    async def _required_source(
        self, session: AsyncSession, organization_id: UUID, source_id: UUID
    ) -> KnowledgeSource:
        source = await self._repository.get_source(session, organization_id, source_id)
        if source is None:
            raise KnowledgeSourceNotFoundError
        return source

    @staticmethod
    def _encode_cursor(source: KnowledgeSource) -> str:
        payload = json.dumps(
            {"created_at": source.created_at.isoformat(), "id": str(source.id)},
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(value: str) -> tuple[datetime, UUID]:
        try:
            padding = "=" * (-len(value) % 4)
            payload = json.loads(base64.urlsafe_b64decode(value + padding))
            if not isinstance(payload, dict):
                raise ValueError
            created_at = datetime.fromisoformat(cast(str, payload["created_at"]))
            source_id = UUID(cast(str, payload["id"]))
            if created_at.tzinfo is None:
                raise ValueError
            return created_at, source_id
        except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidKnowledgeCursorError from exc
