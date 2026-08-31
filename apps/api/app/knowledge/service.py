import base64
import binascii
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import (
    InvalidKnowledgeCursorError,
    KnowledgeContentUnavailableError,
    KnowledgeProcessingInProgressError,
    KnowledgeProcessingNotRetryableError,
    KnowledgeSourceKindError,
    KnowledgeSourceNotFoundError,
    KnowledgeStorageUnavailableError,
)
from app.knowledge.models import (
    ExtractedContent,
    KnowledgeDeletionPlan,
    KnowledgeFileObject,
    KnowledgeProcessingStatus,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourcePage,
)
from app.knowledge.normalization import article_locator_map, normalize_text
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.storage import knowledge_storage_key
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

    async def create_document_processing(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        title: str,
        description: str | None,
        original_filename: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
    ) -> tuple[KnowledgeSource, KnowledgeFileObject]:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        source_id = self._id_factory()
        version_id = self._id_factory()
        storage_key = knowledge_storage_key(organization_id, source_id, version_id)
        source = await self._repository.create_document_processing(
            session,
            source_id=source_id,
            version_id=version_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            title=title,
            description=description,
            original_filename=original_filename,
            media_type=media_type,
            size_bytes=size_bytes,
            sha256=sha256,
            storage_key=storage_key,
            processing_started_at=self._clock(),
        )
        return source, KnowledgeFileObject(
            version_id=version_id,
            storage_key=storage_key,
            original_filename=original_filename,
            media_type=media_type,
            size_bytes=size_bytes,
        )

    async def mark_document_ready(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        extracted: ExtractedContent,
    ) -> KnowledgeSource:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        source = await self._repository.mark_document_ready(
            session,
            organization_id=organization_id,
            source_id=source_id,
            normalized_text=extracted.normalized_text,
            locator_map=extracted.locator_map,
            extractor_name=extracted.extractor_name,
            extractor_version=extracted.extractor_version,
            processed_at=self._clock(),
        )
        if source is None:
            raise KnowledgeSourceNotFoundError
        return source

    async def mark_document_failed(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        failure_code: str,
        failure_message: str,
    ) -> KnowledgeSource:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        source = await self._repository.mark_document_failed(
            session,
            organization_id=organization_id,
            source_id=source_id,
            failure_code=failure_code,
            failure_message=failure_message,
            processed_at=self._clock(),
        )
        if source is None:
            raise KnowledgeSourceNotFoundError
        return source

    async def begin_document_retry(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        stale_after_seconds: int,
    ) -> tuple[KnowledgeSource, KnowledgeFileObject]:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        current = await self._required_source(session, organization_id, source_id)
        if current.kind != "document":
            raise KnowledgeSourceKindError
        version = current.current_version
        if version.status == "ready":
            raise KnowledgeProcessingNotRetryableError
        now = self._clock()
        if (
            version.status == "processing"
            and version.processing_started_at is not None
            and version.processing_started_at > now - timedelta(seconds=stale_after_seconds)
        ):
            raise KnowledgeProcessingInProgressError
        source = await self._repository.begin_document_retry(
            session,
            organization_id=organization_id,
            source_id=source_id,
            processing_started_at=now,
        )
        if source is None:
            raise KnowledgeSourceNotFoundError
        file_object = await self._current_file_object(session, source)
        return source, file_object

    async def get_file_for_download(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> KnowledgeFileObject:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        source = await self._required_source(session, organization_id, source_id)
        if source.kind != "document":
            raise KnowledgeSourceKindError
        return await self._current_file_object(session, source)

    async def prepare_deletion(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> KnowledgeDeletionPlan:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        source = await self._required_source(session, organization_id, source_id)
        file_objects = (
            list(await self._repository.get_file_objects(session, organization_id, source_id))
            if source.kind == "document"
            else []
        )
        return KnowledgeDeletionPlan(source=source, file_objects=file_objects)

    async def delete_source(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> None:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        if not await self._repository.delete_source(session, organization_id, source_id):
            raise KnowledgeSourceNotFoundError

    async def _current_file_object(
        self, session: AsyncSession, source: KnowledgeSource
    ) -> KnowledgeFileObject:
        file_objects = await self._repository.get_file_objects(
            session, source.organization_id, source.id
        )
        for file_object in file_objects:
            if file_object.version_id == source.current_version.id:
                return file_object
        raise KnowledgeStorageUnavailableError

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
