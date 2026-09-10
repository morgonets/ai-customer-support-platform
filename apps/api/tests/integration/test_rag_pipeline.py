import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.knowledge.repository import SqlAlchemyKnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.rag.chunking import ReferenceChunker
from app.rag.providers import (
    DeterministicEmbeddingProvider,
    DeterministicGenerationProvider,
    LoggingRagTelemetry,
)
from app.rag.repository import RagRepository, WorkerRagRepository
from app.rag.service import RagService
from app.tenants.authorization import TenantAuthorizer
from app.tenants.errors import OrganizationNotFoundError
from app.tenants.repository import SqlAlchemyTenantRepository
from app.tenants.service import TenantService

ADMIN_DATABASE_URL = os.getenv("INTEGRATION_DATABASE_ADMIN_URL")
OWNER_ID = UUID("91000000-0000-0000-0000-000000000001")
OUTSIDER_ID = UUID("91000000-0000-0000-0000-000000000002")
ORGANIZATION_ID = UUID("92000000-0000-0000-0000-000000000001")
MEMBERSHIP_ID = UUID("93000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("94000000-0000-0000-0000-000000000001")
VERSION_ONE_ID = UUID("95000000-0000-0000-0000-000000000001")
VERSION_TWO_ID = UUID("95000000-0000-0000-0000-000000000002")
PROFILE_TWO_ID = UUID("96000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 9, 9, tzinfo=UTC)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        ADMIN_DATABASE_URL is None,
        reason="INTEGRATION_DATABASE_ADMIN_URL is required for RAG integration tests",
    ),
]


async def _assume_actor(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(text("reset role"))
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"}, separators=(",", ":"))
    await session.execute(
        text("select set_config('request.jwt.claims', :claims, true)"), {"claims": claims}
    )
    await session.execute(text("set local role app_api"))


async def _process_claimed(session: AsyncSession, repository: WorkerRagRepository) -> UUID:
    claimed = await repository.claim(session, worker_id="integration-worker", lease_seconds=300)
    assert claimed is not None
    chunker = ReferenceChunker()
    chunk_set = chunker.chunk(
        organization_id=claimed.organization_id,
        source_id=claimed.source_id,
        version_id=claimed.version_id,
        normalized_text=claimed.normalized_text,
        normalization_version=claimed.normalization_version,
        locator_map=claimed.locator_map,
    )
    embeddings = await DeterministicEmbeddingProvider().embed_documents(
        [chunk.content for chunk in chunk_set.chunks],
        model=claimed.profile.model,
        dimensions=claimed.profile.dimensions,
    )
    await repository.replace_artifacts(
        session,
        generation=claimed,
        chunk_set=chunk_set,
        embeddings=embeddings,
        chunker=chunker,
    )
    assert await repository.complete(
        session,
        generation=claimed,
        chunk_set_id=chunk_set.id,
        chunk_count=len(chunk_set.chunks),
        input_tokens=None,
    )
    return claimed.version_id


async def _exercise_rag_pipeline() -> None:
    assert ADMIN_DATABASE_URL is not None
    engine = create_async_engine(ADMIN_DATABASE_URL)
    session = AsyncSession(engine, expire_on_commit=False)
    transaction = await session.begin()
    tenant_repository = SqlAlchemyTenantRepository()
    knowledge_repository = SqlAlchemyKnowledgeRepository()
    authorizer = TenantAuthorizer(tenant_repository)
    knowledge_ids = iter([SOURCE_ID, VERSION_ONE_ID, VERSION_TWO_ID])
    knowledge = KnowledgeService(
        knowledge_repository,
        authorizer,
        id_factory=lambda: next(knowledge_ids),
        clock=lambda: NOW,
    )
    rag_repository = RagRepository()
    rag = RagService(
        rag_repository,
        knowledge_repository,
        authorizer,
        {"deterministic": DeterministicEmbeddingProvider()},
        DeterministicGenerationProvider(),
        LoggingRagTelemetry(),
        default_profile_key="deterministic-local-v1",
        minimum_vector_similarity=-1,
        candidate_limit=10,
        evidence_limit=4,
        maximum_per_source=2,
    )
    worker_repository = WorkerRagRepository()
    try:
        await session.execute(
            text(
                """
                insert into auth.users (
                  id, email, raw_app_meta_data, raw_user_meta_data, created_at, updated_at
                ) values
                  (:owner_id, 'rag-owner@example.test', '{}', '{}', now(), now()),
                  (:outsider_id, 'rag-outsider@example.test', '{}', '{}', now(), now())
                """
            ),
            {"owner_id": OWNER_ID, "outsider_id": OUTSIDER_ID},
        )
        await session.execute(
            text(
                """
                insert into app.rag_embedding_profiles (
                  id, profile_key, fingerprint, provider, model, model_revision, dimensions
                ) values (
                  :id, 'deterministic-local-8-v2', :fingerprint,
                  'deterministic', 'hash-v1', '2', 8
                )
                """
            ),
            {"id": PROFILE_TWO_ID, "fingerprint": "d" * 64},
        )
        await _assume_actor(session, OWNER_ID)
        tenant_ids = iter([ORGANIZATION_ID, MEMBERSHIP_ID])
        tenant = TenantService(tenant_repository, id_factory=lambda: next(tenant_ids))
        await tenant.create_organization(session, OWNER_ID, "RAG Integration")
        source = await knowledge.create_article(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            title="Refund policy",
            description=None,
            raw_text="Refunds are available for 30 days after purchase.",
        )
        generations = await rag.enqueue_ready_source(session, actor_user_id=OWNER_ID, source=source)
        assert len(generations) == 1
        await session.execute(
            text(
                "update app.knowledge_index_generations "
                "set available_at = now() + interval '1 hour' where id = :generation_id"
            ),
            {"generation_id": generations[0].id},
        )

        await session.execute(text("reset role"))
        await session.execute(text("set local role app_rag_worker"))
        assert (
            await worker_repository.claim(
                session, worker_id="integration-worker", lease_seconds=300
            )
            is None
        )
        await _assume_actor(session, OWNER_ID)
        await session.execute(
            text(
                "update app.knowledge_index_generations "
                "set available_at = now() where id = :generation_id"
            ),
            {"generation_id": generations[0].id},
        )
        await session.execute(text("reset role"))
        await session.execute(text("set local role app_rag_worker"))
        assert await _process_claimed(session, worker_repository) == VERSION_ONE_ID

        await _assume_actor(session, OWNER_ID)
        first_answer = await rag.answer(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            question="How long are refunds available?",
        )
        assert not first_answer.insufficient_context
        assert first_answer.citations[0].version_id == VERSION_ONE_ID

        replacement = await knowledge.replace_article_content(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            raw_text="Refunds are available for 60 days after purchase.",
        )
        await rag.enqueue_ready_source(session, actor_user_id=OWNER_ID, source=replacement)
        before_activation = await rag.answer(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            question="How long are refunds available?",
        )
        assert before_activation.citations[0].version_id == VERSION_ONE_ID

        await session.execute(text("reset role"))
        await session.execute(text("set local role app_rag_worker"))
        failed = await worker_repository.claim(
            session, worker_id="integration-worker", lease_seconds=300
        )
        assert failed is not None
        await worker_repository.fail(
            session,
            generation=failed,
            code="synthetic_failure",
            message="Synthetic public integration failure.",
            retry_at=None,
        )

        await _assume_actor(session, OWNER_ID)
        after_failure = await rag.answer(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            question="How long are refunds available?",
        )
        assert after_failure.citations[0].version_id == VERSION_ONE_ID
        failed_generation = next(
            item
            for item in await rag.list_generations(
                session,
                actor_user_id=OWNER_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
            )
            if item.status == "failed"
        )
        await rag.retry(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            generation_id=failed_generation.id,
        )

        await session.execute(text("reset role"))
        await session.execute(text("set local role app_rag_worker"))
        assert await _process_claimed(session, worker_repository) == VERSION_TWO_ID
        await _assume_actor(session, OWNER_ID)
        activated = await rag.answer(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            question="How long are refunds available?",
        )
        assert activated.citations[0].version_id == VERSION_TWO_ID

        staged = await rag.migrate_profile(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            profile_key="deterministic-local-8-v2",
            request_id=None,
        )
        assert len(staged) == 1
        while_staging = await rag.answer(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            question="How long are refunds available?",
        )
        assert while_staging.citations[0].version_id == VERSION_TWO_ID
        await session.execute(text("reset role"))
        await session.execute(text("set local role app_rag_worker"))
        assert await _process_claimed(session, worker_repository) == VERSION_TWO_ID
        await _assume_actor(session, OWNER_ID)
        profile_result = await session.execute(
            text(
                """
                select profile.profile_key
                from app.organization_rag_settings as settings
                inner join app.rag_embedding_profiles as profile
                  on profile.id = settings.active_profile_id
                where settings.organization_id = :organization_id
                """
            ),
            {"organization_id": ORGANIZATION_ID},
        )
        assert profile_result.scalar_one() == "deterministic-local-8-v2"

        await knowledge.delete_source(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
        )
        deleted = await rag.answer(
            session,
            actor_user_id=OWNER_ID,
            organization_id=ORGANIZATION_ID,
            question="How long are refunds available?",
        )
        assert deleted.insufficient_context

        await _assume_actor(session, OUTSIDER_ID)
        with pytest.raises(OrganizationNotFoundError):
            await rag.answer(
                session,
                actor_user_id=OUTSIDER_ID,
                organization_id=ORGANIZATION_ID,
                question="Can I see another tenant?",
            )
    finally:
        await transaction.rollback()
        await session.close()
        await engine.dispose()


def test_rag_build_validate_activate_failure_and_deletion_lifecycle() -> None:
    asyncio.run(_exercise_rag_pipeline())
