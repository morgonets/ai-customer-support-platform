import json
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import (
    KnowledgeProcessingStatus,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceVersion,
)


class KnowledgeRepository(Protocol):
    async def list_sources(
        self,
        session: AsyncSession,
        organization_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        kind: KnowledgeSourceKind | None,
        status: KnowledgeProcessingStatus | None,
    ) -> Sequence[KnowledgeSource]: ...

    async def get_source(
        self, session: AsyncSession, organization_id: UUID, source_id: UUID
    ) -> KnowledgeSource | None: ...

    async def create_article(
        self,
        session: AsyncSession,
        *,
        source_id: UUID,
        version_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        title: str,
        description: str | None,
        raw_text: str,
        normalized_text: str,
        locator_map: dict[str, object],
        processed_at: datetime,
    ) -> KnowledgeSource: ...

    async def update_metadata(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        source_id: UUID,
        actor_user_id: UUID,
        title: str,
        description: str | None,
    ) -> KnowledgeSource | None: ...

    async def replace_article_content(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        source_id: UUID,
        version_id: UUID,
        actor_user_id: UUID,
        raw_text: str,
        normalized_text: str,
        locator_map: dict[str, object],
        processed_at: datetime,
    ) -> KnowledgeSource | None: ...


class SqlAlchemyKnowledgeRepository:
    _source_select = """
        select source.id, source.organization_id, source.kind, source.title,
               source.description, source.created_by_user_id, source.updated_by_user_id,
               source.created_at, source.updated_at,
               version.id as version_id, version.version_number, version.is_current,
               version.status, version.raw_text, version.normalized_text,
               version.normalization_version, version.locator_map,
               version.original_filename, version.media_type, version.size_bytes,
               version.sha256, version.extractor_name, version.extractor_version,
               version.processing_attempts, version.processing_started_at,
               version.processed_at, version.failure_code, version.failure_message,
               version.created_by_user_id as version_created_by_user_id,
               version.created_at as version_created_at,
               version.updated_at as version_updated_at
        from app.knowledge_sources as source
        inner join app.knowledge_source_versions as version
          on version.organization_id = source.organization_id
         and version.source_id = source.id
         and version.is_current
    """

    async def list_sources(
        self,
        session: AsyncSession,
        organization_id: UUID,
        *,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
        kind: KnowledgeSourceKind | None,
        status: KnowledgeProcessingStatus | None,
    ) -> Sequence[KnowledgeSource]:
        predicates = ["source.organization_id = :organization_id"]
        parameters: dict[str, object] = {"organization_id": organization_id, "limit": limit}
        if cursor is not None:
            predicates.append("(source.created_at, source.id) < (:cursor_created_at, :cursor_id)")
            parameters["cursor_created_at"], parameters["cursor_id"] = cursor
        if kind is not None:
            predicates.append("source.kind = :kind")
            parameters["kind"] = kind
        if status is not None:
            predicates.append("version.status = :status")
            parameters["status"] = status
        statement = text(
            f"""
            {self._source_select}
            where {" and ".join(predicates)}
            order by source.created_at desc, source.id desc
            limit :limit
            """
        )
        result = await session.execute(statement, parameters)
        return [self._source(row) for row in result.mappings().all()]

    async def get_source(
        self, session: AsyncSession, organization_id: UUID, source_id: UUID
    ) -> KnowledgeSource | None:
        result = await session.execute(
            text(
                f"""
                {self._source_select}
                where source.organization_id = :organization_id
                  and source.id = :source_id
                """
            ),
            {"organization_id": organization_id, "source_id": source_id},
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._source(row)

    async def create_article(
        self,
        session: AsyncSession,
        *,
        source_id: UUID,
        version_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        title: str,
        description: str | None,
        raw_text: str,
        normalized_text: str,
        locator_map: dict[str, object],
        processed_at: datetime,
    ) -> KnowledgeSource:
        await session.execute(
            text(
                """
                insert into app.knowledge_sources (
                  id, organization_id, kind, title, description,
                  created_by_user_id, updated_by_user_id
                )
                values (
                  :source_id, :organization_id, 'article', :title, :description,
                  :actor_user_id, :actor_user_id
                )
                """
            ),
            {
                "source_id": source_id,
                "organization_id": organization_id,
                "title": title,
                "description": description,
                "actor_user_id": actor_user_id,
            },
        )
        await self._insert_article_version(
            session,
            version_id=version_id,
            organization_id=organization_id,
            source_id=source_id,
            version_number=1,
            actor_user_id=actor_user_id,
            raw_text=raw_text,
            normalized_text=normalized_text,
            locator_map=locator_map,
            processed_at=processed_at,
        )
        source = await self.get_source(session, organization_id, source_id)
        if source is None:
            raise RuntimeError("created knowledge article is not visible")
        return source

    async def update_metadata(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        source_id: UUID,
        actor_user_id: UUID,
        title: str,
        description: str | None,
    ) -> KnowledgeSource | None:
        result = await session.execute(
            text(
                """
                update app.knowledge_sources
                set title = :title,
                    description = :description,
                    updated_by_user_id = :actor_user_id
                where organization_id = :organization_id
                  and id = :source_id
                returning id
                """
            ),
            {
                "organization_id": organization_id,
                "source_id": source_id,
                "actor_user_id": actor_user_id,
                "title": title,
                "description": description,
            },
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_source(session, organization_id, source_id)

    async def replace_article_content(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        source_id: UUID,
        version_id: UUID,
        actor_user_id: UUID,
        raw_text: str,
        normalized_text: str,
        locator_map: dict[str, object],
        processed_at: datetime,
    ) -> KnowledgeSource | None:
        locked = await session.execute(
            text(
                """
                select id
                from app.knowledge_sources
                where organization_id = :organization_id
                  and id = :source_id
                  and kind = 'article'
                for update
                """
            ),
            {"organization_id": organization_id, "source_id": source_id},
        )
        if locked.scalar_one_or_none() is None:
            return None
        number_result = await session.execute(
            text(
                """
                select max(version_number)
                from app.knowledge_source_versions
                where organization_id = :organization_id
                  and source_id = :source_id
                """
            ),
            {"organization_id": organization_id, "source_id": source_id},
        )
        next_number = cast(int, number_result.scalar_one()) + 1
        await session.execute(
            text(
                """
                update app.knowledge_source_versions
                set is_current = false
                where organization_id = :organization_id
                  and source_id = :source_id
                  and is_current
                """
            ),
            {"organization_id": organization_id, "source_id": source_id},
        )
        await self._insert_article_version(
            session,
            version_id=version_id,
            organization_id=organization_id,
            source_id=source_id,
            version_number=next_number,
            actor_user_id=actor_user_id,
            raw_text=raw_text,
            normalized_text=normalized_text,
            locator_map=locator_map,
            processed_at=processed_at,
        )
        return await self.get_source(session, organization_id, source_id)

    @staticmethod
    async def _insert_article_version(
        session: AsyncSession,
        *,
        version_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        version_number: int,
        actor_user_id: UUID,
        raw_text: str,
        normalized_text: str,
        locator_map: dict[str, object],
        processed_at: datetime,
    ) -> None:
        await session.execute(
            text(
                """
                insert into app.knowledge_source_versions (
                  id, organization_id, source_id, kind, version_number, status,
                  raw_text, normalized_text, normalization_version, locator_map,
                  extractor_name, extractor_version, processing_attempts, processed_at,
                  created_by_user_id
                )
                values (
                  :version_id, :organization_id, :source_id, 'article', :version_number, 'ready',
                  :raw_text, :normalized_text, 1, cast(:locator_map as jsonb),
                  'manual', '1', 0, :processed_at, :actor_user_id
                )
                """
            ),
            {
                "version_id": version_id,
                "organization_id": organization_id,
                "source_id": source_id,
                "version_number": version_number,
                "raw_text": raw_text,
                "normalized_text": normalized_text,
                "locator_map": json.dumps(locator_map, separators=(",", ":")),
                "processed_at": processed_at,
                "actor_user_id": actor_user_id,
            },
        )

    @classmethod
    def _source(cls, row: RowMapping) -> KnowledgeSource:
        source_id = cast(UUID, row["id"])
        organization_id = cast(UUID, row["organization_id"])
        kind = cast(KnowledgeSourceKind, row["kind"])
        return KnowledgeSource(
            id=source_id,
            organization_id=organization_id,
            kind=kind,
            title=cast(str, row["title"]),
            description=cast(str | None, row["description"]),
            created_by_user_id=cast(UUID | None, row["created_by_user_id"]),
            updated_by_user_id=cast(UUID | None, row["updated_by_user_id"]),
            created_at=cast(datetime, row["created_at"]),
            updated_at=cast(datetime, row["updated_at"]),
            current_version=KnowledgeSourceVersion(
                id=cast(UUID, row["version_id"]),
                organization_id=organization_id,
                source_id=source_id,
                kind=kind,
                version_number=cast(int, row["version_number"]),
                is_current=cast(bool, row["is_current"]),
                status=cast(KnowledgeProcessingStatus, row["status"]),
                raw_text=cast(str | None, row["raw_text"]),
                normalized_text=cast(str | None, row["normalized_text"]),
                normalization_version=cast(int, row["normalization_version"]),
                locator_map=cast(dict[str, object] | None, row["locator_map"]),
                original_filename=cast(str | None, row["original_filename"]),
                media_type=cast(str | None, row["media_type"]),
                size_bytes=cast(int | None, row["size_bytes"]),
                sha256=cast(str | None, row["sha256"]),
                extractor_name=cast(str | None, row["extractor_name"]),
                extractor_version=cast(str | None, row["extractor_version"]),
                processing_attempts=cast(int, row["processing_attempts"]),
                processing_started_at=cast(datetime | None, row["processing_started_at"]),
                processed_at=cast(datetime | None, row["processed_at"]),
                failure_code=cast(str | None, row["failure_code"]),
                failure_message=cast(str | None, row["failure_message"]),
                created_by_user_id=cast(UUID | None, row["version_created_by_user_id"]),
                created_at=cast(datetime, row["version_created_at"]),
                updated_at=cast(datetime, row["version_updated_at"]),
            ),
        )
