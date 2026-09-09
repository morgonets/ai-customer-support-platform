import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.chunking import CHUNKER_NAME, CHUNKER_VERSION, ReferenceChunker
from app.rag.models import (
    ChunkSet,
    ClaimedGeneration,
    EmbeddingProfile,
    IndexGeneration,
    RetrievalCandidate,
)


def vector_literal(vector: Sequence[float]) -> str:
    if not vector:
        raise ValueError("vector must not be empty")
    return "[" + ",".join(format(value, ".17g") for value in vector) + "]"


class RagRepository:
    async def ensure_settings_and_enqueue(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        source_id: UUID,
        version_id: UUID,
        actor_user_id: UUID,
        profile_key: str,
        request_id: UUID | None = None,
    ) -> tuple[IndexGeneration, ...]:
        profile = await self.get_profile(session, profile_key)
        if profile is None:
            return ()
        await session.execute(
            text(
                """
                insert into app.organization_rag_settings (
                  organization_id, active_profile_id, updated_by_user_id
                ) values (:organization_id, :profile_id, :actor_user_id)
                on conflict (organization_id) do nothing
                """
            ),
            {
                "organization_id": organization_id,
                "profile_id": profile.id,
                "actor_user_id": actor_user_id,
            },
        )
        profiles_result = await session.execute(
            text(
                """
                select active_profile_id, staging_profile_id
                from app.organization_rag_settings
                where organization_id = :organization_id
                """
            ),
            {"organization_id": organization_id},
        )
        settings = profiles_result.mappings().one()
        profile_ids = {cast(UUID, settings["active_profile_id"])}
        staging = cast(UUID | None, settings["staging_profile_id"])
        if staging is not None:
            profile_ids.add(staging)
        generations = []
        for profile_id in sorted(profile_ids, key=str):
            generations.append(
                await self._enqueue(
                    session,
                    organization_id=organization_id,
                    source_id=source_id,
                    version_id=version_id,
                    profile_id=profile_id,
                    actor_user_id=actor_user_id,
                    request_id=request_id,
                    reuse_existing=True,
                )
            )
        return tuple(generations)

    async def enqueue_reindex(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        source_id: UUID,
        version_id: UUID,
        actor_user_id: UUID,
        profile_id: UUID,
        request_id: UUID | None,
    ) -> IndexGeneration:
        return await self._enqueue(
            session,
            organization_id=organization_id,
            source_id=source_id,
            version_id=version_id,
            profile_id=profile_id,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reuse_existing=False,
        )

    async def _enqueue(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        source_id: UUID,
        version_id: UUID,
        profile_id: UUID,
        actor_user_id: UUID,
        request_id: UUID | None,
        reuse_existing: bool,
    ) -> IndexGeneration:
        await session.execute(
            text(
                """
                select id from app.knowledge_sources
                where organization_id = :organization_id and id = :source_id
                for update
                """
            ),
            {"organization_id": organization_id, "source_id": source_id},
        )
        if reuse_existing:
            existing = await session.execute(
                text(
                    """
                    select generation.*, profile.profile_key
                    from app.knowledge_index_generations as generation
                    inner join app.rag_embedding_profiles as profile
                      on profile.id = generation.embedding_profile_id
                    where generation.organization_id = :organization_id
                      and generation.source_id = :source_id
                      and generation.knowledge_source_version_id = :version_id
                      and generation.embedding_profile_id = :profile_id
                      and generation.status in ('queued', 'processing', 'ready')
                    order by generation.generation_number desc
                    limit 1
                    """
                ),
                {
                    "organization_id": organization_id,
                    "source_id": source_id,
                    "version_id": version_id,
                    "profile_id": profile_id,
                },
            )
            row = existing.mappings().one_or_none()
            if row is not None:
                return self._generation(row)
        number_result = await session.execute(
            text(
                """
                select coalesce(max(generation_number), 0) + 1
                from app.knowledge_index_generations
                where organization_id = :organization_id and source_id = :source_id
                  and embedding_profile_id = :profile_id
                """
            ),
            {
                "organization_id": organization_id,
                "source_id": source_id,
                "profile_id": profile_id,
            },
        )
        generation_id = uuid4()
        generation_number = cast(int, number_result.scalar_one())
        inserted = await session.execute(
            text(
                """
                insert into app.knowledge_index_generations (
                  id, organization_id, source_id, knowledge_source_version_id,
                  embedding_profile_id, generation_number, requested_by_user_id, request_id
                ) values (
                  :id, :organization_id, :source_id, :version_id,
                  :profile_id, :generation_number, :actor_user_id, :request_id
                )
                returning *
                """
            ),
            {
                "id": generation_id,
                "organization_id": organization_id,
                "source_id": source_id,
                "version_id": version_id,
                "profile_id": profile_id,
                "generation_number": generation_number,
                "actor_user_id": actor_user_id,
                "request_id": request_id,
            },
        )
        row_values = dict(inserted.mappings().one())
        profile_result = await session.execute(
            text("select profile_key from app.rag_embedding_profiles where id = :profile_id"),
            {"profile_id": profile_id},
        )
        row_values["profile_key"] = profile_result.scalar_one()
        return self._generation(row_values)

    async def get_profile(self, session: AsyncSession, profile_key: str) -> EmbeddingProfile | None:
        result = await session.execute(
            text(
                """
                select id, profile_key, provider, model, model_revision, dimensions
                from app.rag_embedding_profiles where profile_key = :profile_key
                """
            ),
            {"profile_key": profile_key},
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._profile(row)

    async def get_active_profile(
        self, session: AsyncSession, organization_id: UUID
    ) -> EmbeddingProfile | None:
        result = await session.execute(
            text(
                """
                select profile.id, profile.profile_key, profile.provider, profile.model,
                       profile.model_revision, profile.dimensions
                from app.organization_rag_settings as settings
                inner join app.rag_embedding_profiles as profile
                  on profile.id = settings.active_profile_id
                where settings.organization_id = :organization_id
                """
            ),
            {"organization_id": organization_id},
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._profile(row)

    async def list_generations(
        self, session: AsyncSession, organization_id: UUID, source_id: UUID
    ) -> tuple[IndexGeneration, ...]:
        result = await session.execute(
            text(
                """
                select generation.*, profile.profile_key
                from app.knowledge_index_generations as generation
                inner join app.rag_embedding_profiles as profile
                  on profile.id = generation.embedding_profile_id
                where generation.organization_id = :organization_id
                  and generation.source_id = :source_id
                order by generation.created_at desc, generation.id desc
                """
            ),
            {"organization_id": organization_id, "source_id": source_id},
        )
        return tuple(self._generation(row) for row in result.mappings())

    async def retry_generation(
        self, session: AsyncSession, organization_id: UUID, generation_id: UUID
    ) -> IndexGeneration | None:
        result = await session.execute(
            text(
                """
                update app.knowledge_index_generations as generation
                set status = 'queued', available_at = now(), failure_code = null,
                    failure_message = null, completed_at = null
                from app.rag_embedding_profiles as profile
                where generation.organization_id = :organization_id
                  and generation.id = :generation_id
                  and generation.embedding_profile_id = profile.id
                  and generation.status = 'failed'
                returning generation.*, profile.profile_key
                """
            ),
            {"organization_id": organization_id, "generation_id": generation_id},
        )
        row = result.mappings().one_or_none()
        return None if row is None else self._generation(row)

    async def begin_profile_migration(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        profile_key: str,
        request_id: UUID | None,
    ) -> tuple[IndexGeneration, ...]:
        profile = await self.get_profile(session, profile_key)
        if profile is None:
            return ()
        settings_result = await session.execute(
            text(
                """
                update app.organization_rag_settings
                set staging_profile_id = :profile_id, updated_by_user_id = :actor_user_id
                where organization_id = :organization_id
                  and active_profile_id <> :profile_id
                returning organization_id
                """
            ),
            {
                "organization_id": organization_id,
                "profile_id": profile.id,
                "actor_user_id": actor_user_id,
            },
        )
        if settings_result.scalar_one_or_none() is None:
            return ()
        versions = await session.execute(
            text(
                """
                select source.id as source_id, version.id as version_id
                from app.knowledge_sources as source
                inner join app.knowledge_source_versions as version
                  on version.organization_id = source.organization_id
                 and version.source_id = source.id and version.is_current
                where source.organization_id = :organization_id and version.status = 'ready'
                order by source.id
                """
            ),
            {"organization_id": organization_id},
        )
        generations = []
        for row in versions.mappings():
            generations.append(
                await self._enqueue(
                    session,
                    organization_id=organization_id,
                    source_id=cast(UUID, row["source_id"]),
                    version_id=cast(UUID, row["version_id"]),
                    profile_id=profile.id,
                    actor_user_id=actor_user_id,
                    request_id=request_id,
                    reuse_existing=True,
                )
            )
        return tuple(generations)

    async def retrieve_vector(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        profile_id: UUID,
        query_vector: Sequence[float],
        limit: int,
        exact: bool,
    ) -> tuple[RetrievalCandidate, ...]:
        if exact:
            await session.execute(text("set local enable_indexscan = off"))
            await session.execute(text("set local enable_bitmapscan = off"))
        result = await session.execute(
            text(
                """
                select chunk.id as chunk_id, chunk.source_id,
                       chunk.knowledge_source_version_id as version_id,
                       version.version_number, source.title as source_title,
                       source.kind as source_kind, chunk.content, chunk.locator,
                       1 - (embedding.embedding <=> cast(:query_vector as extensions.vector))
                         as vector_score
                from app.knowledge_chunk_embeddings as embedding
                inner join app.knowledge_index_generations as generation
                  on generation.organization_id = embedding.organization_id
                 and generation.id = embedding.generation_id
                inner join app.knowledge_chunks as chunk
                  on chunk.organization_id = embedding.organization_id
                 and chunk.source_id = embedding.source_id
                 and chunk.knowledge_source_version_id = embedding.knowledge_source_version_id
                 and chunk.id = embedding.chunk_id
                inner join app.knowledge_sources as source
                  on source.organization_id = chunk.organization_id and source.id = chunk.source_id
                inner join app.knowledge_source_versions as version
                  on version.organization_id = chunk.organization_id
                 and version.source_id = chunk.source_id
                 and version.id = chunk.knowledge_source_version_id
                where embedding.organization_id = :organization_id
                  and embedding.embedding_profile_id = :profile_id
                  and generation.status = 'ready' and generation.is_active
                order by embedding.embedding <=> cast(:query_vector as extensions.vector), chunk.id
                limit :limit
                """
            ),
            {
                "organization_id": organization_id,
                "profile_id": profile_id,
                "query_vector": vector_literal(query_vector),
                "limit": limit,
            },
        )
        return tuple(self._candidate(row) for row in result.mappings())

    async def retrieve_lexical(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        question: str,
        limit: int,
    ) -> tuple[RetrievalCandidate, ...]:
        result = await session.execute(
            text(
                """
                with query as (select websearch_to_tsquery('simple', :question) as value)
                select chunk.id as chunk_id, chunk.source_id,
                       chunk.knowledge_source_version_id as version_id,
                       version.version_number, source.title as source_title,
                       source.kind as source_kind, chunk.content, chunk.locator,
                       ts_rank_cd(chunk.search_vector, query.value) as lexical_score
                from app.knowledge_chunks as chunk
                cross join query
                inner join app.knowledge_index_generations as generation
                  on generation.organization_id = chunk.organization_id
                 and generation.chunk_set_id = chunk.chunk_set_id
                inner join app.knowledge_sources as source
                  on source.organization_id = chunk.organization_id and source.id = chunk.source_id
                inner join app.knowledge_source_versions as version
                  on version.organization_id = chunk.organization_id
                 and version.source_id = chunk.source_id
                 and version.id = chunk.knowledge_source_version_id
                where chunk.organization_id = :organization_id
                  and generation.status = 'ready' and generation.is_active
                  and chunk.search_vector @@ query.value
                order by lexical_score desc, chunk.id
                limit :limit
                """
            ),
            {"organization_id": organization_id, "question": question, "limit": limit},
        )
        return tuple(self._candidate(row) for row in result.mappings())

    @staticmethod
    def _profile(row: RowMapping | Mapping[str, Any]) -> EmbeddingProfile:
        return EmbeddingProfile(
            id=cast(UUID, row["id"]),
            profile_key=cast(str, row["profile_key"]),
            provider=cast(str, row["provider"]),
            model=cast(str, row["model"]),
            model_revision=cast(str | None, row["model_revision"]),
            dimensions=cast(int, row["dimensions"]),
        )

    @staticmethod
    def _generation(row: RowMapping | Mapping[str, Any]) -> IndexGeneration:
        return IndexGeneration(
            id=cast(UUID, row["id"]),
            version_id=cast(UUID, row["knowledge_source_version_id"]),
            profile_key=cast(str, row["profile_key"]),
            generation_number=cast(int, row["generation_number"]),
            status=cast(Any, row["status"]),
            is_active=cast(bool, row["is_active"]),
            attempt_count=cast(int, row["attempt_count"]),
            failure_code=cast(str | None, row["failure_code"]),
            failure_message=cast(str | None, row["failure_message"]),
            created_at=cast(datetime, row["created_at"]),
            completed_at=cast(datetime | None, row["completed_at"]),
        )

    @staticmethod
    def _candidate(row: RowMapping | Mapping[str, Any]) -> RetrievalCandidate:
        locator = row["locator"]
        if isinstance(locator, str):
            locator = json.loads(locator)
        return RetrievalCandidate(
            chunk_id=cast(UUID, row["chunk_id"]),
            source_id=cast(UUID, row["source_id"]),
            version_id=cast(UUID, row["version_id"]),
            version_number=cast(int, row["version_number"]),
            source_title=cast(str, row["source_title"]),
            source_kind=cast(str, row["source_kind"]),
            content=cast(str, row["content"]),
            locator=cast(dict[str, Any], locator),
            vector_score=cast(float | None, row.get("vector_score")),
            lexical_score=cast(float | None, row.get("lexical_score")),
        )


class WorkerRagRepository:
    async def claim(
        self, session: AsyncSession, *, worker_id: str, lease_seconds: int
    ) -> ClaimedGeneration | None:
        result = await session.execute(
            text("select * from app_private.claim_rag_generation(:worker_id, :lease_seconds)"),
            {"worker_id": worker_id, "lease_seconds": lease_seconds},
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        await session.execute(
            text("select set_config('app.rag_lease_token', :lease_token, true)"),
            {"lease_token": str(row["lease_token"])},
        )
        locator = row["locator_map"]
        if isinstance(locator, str):
            locator = json.loads(locator)
        return ClaimedGeneration(
            id=cast(UUID, row["generation_id"]),
            organization_id=cast(UUID, row["organization_id"]),
            source_id=cast(UUID, row["source_id"]),
            version_id=cast(UUID, row["knowledge_source_version_id"]),
            profile=EmbeddingProfile(
                id=cast(UUID, row["embedding_profile_id"]),
                profile_key=cast(str, row["profile_key"]),
                provider=cast(str, row["provider"]),
                model=cast(str, row["model"]),
                model_revision=cast(str | None, row["model_revision"]),
                dimensions=cast(int, row["dimensions"]),
            ),
            attempt_count=cast(int, row["attempt_count"]),
            lease_token=cast(UUID, row["lease_token"]),
            normalized_text=cast(str, row["normalized_text"]),
            normalization_version=cast(int, row["normalization_version"]),
            locator_map=cast(dict[str, Any], locator),
        )

    async def replace_artifacts(
        self,
        session: AsyncSession,
        *,
        generation: ClaimedGeneration,
        chunk_set: ChunkSet,
        embeddings: Sequence[Sequence[float]],
        chunker: ReferenceChunker,
    ) -> None:
        await session.execute(
            text(
                "delete from app.knowledge_chunk_embeddings "
                "where organization_id = :organization_id and generation_id = :generation_id"
            ),
            {"organization_id": generation.organization_id, "generation_id": generation.id},
        )
        await session.execute(
            text(
                """
                insert into app.knowledge_chunk_sets (
                  id, organization_id, source_id, knowledge_source_version_id,
                  chunker_name, chunker_version, chunker_config, chunker_fingerprint,
                  normalization_version, normalized_content_sha256, chunk_count
                ) values (
                  :id, :organization_id, :source_id, :version_id,
                  :chunker_name, :chunker_version, cast(:chunker_config as jsonb), :fingerprint,
                  :normalization_version, :content_hash, :chunk_count
                )
                on conflict (organization_id, knowledge_source_version_id, chunker_fingerprint)
                do nothing
                """
            ),
            {
                "id": chunk_set.id,
                "organization_id": generation.organization_id,
                "source_id": generation.source_id,
                "version_id": generation.version_id,
                "chunker_name": CHUNKER_NAME,
                "chunker_version": CHUNKER_VERSION,
                "chunker_config": json.dumps(chunker.config, separators=(",", ":")),
                "fingerprint": chunk_set.fingerprint,
                "normalization_version": generation.normalization_version,
                "content_hash": chunk_set.normalized_content_sha256,
                "chunk_count": len(chunk_set.chunks),
            },
        )
        for chunk, embedding in zip(chunk_set.chunks, embeddings, strict=True):
            await session.execute(
                text(
                    """
                    insert into app.knowledge_chunks (
                      id, organization_id, source_id, knowledge_source_version_id,
                      chunk_set_id, ordinal, content, start_char, end_char,
                      content_sha256, locator
                    ) values (
                      :id, :organization_id, :source_id, :version_id,
                      :chunk_set_id, :ordinal, :content, :start_char, :end_char,
                      :content_hash, cast(:locator as jsonb)
                    )
                    on conflict (id) do nothing
                    """
                ),
                {
                    "id": chunk.id,
                    "organization_id": generation.organization_id,
                    "source_id": generation.source_id,
                    "version_id": generation.version_id,
                    "chunk_set_id": chunk_set.id,
                    "ordinal": chunk.ordinal,
                    "content": chunk.content,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    "content_hash": chunk.content_sha256,
                    "locator": json.dumps(chunk.locator, separators=(",", ":")),
                },
            )
            await session.execute(
                text(
                    """
                    insert into app.knowledge_chunk_embeddings (
                      organization_id, source_id, knowledge_source_version_id,
                      generation_id, chunk_id, embedding_profile_id,
                      embedding_dimensions, embedding
                    ) values (
                      :organization_id, :source_id, :version_id,
                      :generation_id, :chunk_id, :profile_id,
                      :dimensions, cast(:embedding as extensions.vector)
                    )
                    """
                ),
                {
                    "organization_id": generation.organization_id,
                    "source_id": generation.source_id,
                    "version_id": generation.version_id,
                    "generation_id": generation.id,
                    "chunk_id": chunk.id,
                    "profile_id": generation.profile.id,
                    "dimensions": generation.profile.dimensions,
                    "embedding": vector_literal(embedding),
                },
            )

    async def complete(
        self,
        session: AsyncSession,
        *,
        generation: ClaimedGeneration,
        chunk_set_id: UUID,
        chunk_count: int,
        input_tokens: int | None,
    ) -> bool:
        result = await session.execute(
            text(
                "select app_private.complete_rag_generation("
                ":generation_id, :lease_token, :chunk_set_id, :chunk_count, :input_tokens)"
            ),
            {
                "generation_id": generation.id,
                "lease_token": generation.lease_token,
                "chunk_set_id": chunk_set_id,
                "chunk_count": chunk_count,
                "input_tokens": input_tokens,
            },
        )
        return cast(bool, result.scalar_one())

    async def fail(
        self,
        session: AsyncSession,
        *,
        generation: ClaimedGeneration,
        code: str,
        message: str,
        retry_at: datetime | None,
    ) -> None:
        await session.execute(
            text(
                "select app_private.fail_rag_generation("
                ":generation_id, :lease_token, :code, :message, :retry_at)"
            ),
            {
                "generation_id": generation.id,
                "lease_token": generation.lease_token,
                "code": code,
                "message": message,
                "retry_at": retry_at,
            },
        )
