import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import KnowledgeSourceNotFoundError
from app.knowledge.models import KnowledgeProcessingStatus, KnowledgeSource, KnowledgeSourceVersion
from app.knowledge.repository import KnowledgeRepository
from app.rag.errors import (
    RagGenerationNotFoundError,
    RagNotConfiguredError,
    RagProfileNotFoundError,
    RagProviderUnavailableError,
)
from app.rag.models import (
    EmbeddingProfile,
    GeneratedPart,
    GenerationResult,
    IndexGeneration,
    RetrievalCandidate,
)
from app.rag.ports import EmbeddingProvider, GenerationProvider, RagTelemetry
from app.rag.providers import ProviderError
from app.rag.repository import RagRepository
from app.rag.service import INSUFFICIENT_CONTEXT_ANSWER, RagService, reciprocal_rank_fusion
from app.tenants.authorization import TenantAuthorizer
from app.tenants.models import TenantContext

NOW = datetime(2026, 9, 9, tzinfo=UTC)
ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("30000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("40000000-0000-0000-0000-000000000001")
PROFILE_ID = UUID("50000000-0000-0000-0000-000000000001")
GENERATION_ID = UUID("60000000-0000-0000-0000-000000000001")


def _source(*, status: KnowledgeProcessingStatus = "ready") -> KnowledgeSource:
    return KnowledgeSource(
        id=SOURCE_ID,
        organization_id=ORGANIZATION_ID,
        kind="article",
        title="Returns",
        description=None,
        created_by_user_id=ACTOR_ID,
        updated_by_user_id=ACTOR_ID,
        created_at=NOW,
        updated_at=NOW,
        current_version=KnowledgeSourceVersion(
            id=VERSION_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            kind="article",
            version_number=2,
            is_current=True,
            status=status,
            raw_text="Returns take 30 days.",
            normalized_text="Returns take 30 days.",
            normalization_version=1,
            locator_map={"schema_version": 1},
            original_filename=None,
            media_type=None,
            size_bytes=None,
            sha256=None,
            extractor_name="manual",
            extractor_version="1",
            processing_attempts=0,
            processing_started_at=None,
            processed_at=NOW,
            failure_code=None,
            failure_message=None,
            created_by_user_id=ACTOR_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(PROFILE_ID, "local", "test", "model", None, 2)


def _generation(generation_id: UUID = GENERATION_ID) -> IndexGeneration:
    return IndexGeneration(
        id=generation_id,
        version_id=VERSION_ID,
        profile_key="local",
        generation_number=1,
        status="queued",
        is_active=False,
        attempt_count=0,
        failure_code=None,
        failure_message=None,
        created_at=NOW,
        completed_at=None,
    )


def _candidate(
    number: int, *, source_id: UUID = SOURCE_ID, vector: float | None = None
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=UUID(f"70000000-0000-0000-0000-{number:012d}"),
        source_id=source_id,
        version_id=VERSION_ID,
        version_number=2,
        source_title="Returns",
        source_kind="article",
        content=f"Evidence {number}",
        locator={"schema_version": 1, "locations": [{"kind": "text", "start": 0, "end": 10}]},
        vector_score=vector,
        lexical_score=1 if vector is None else None,
    )


def _service() -> tuple[
    RagService, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock
]:
    repository = MagicMock(spec=RagRepository)
    knowledge = MagicMock(spec=KnowledgeRepository)
    knowledge.get_source.return_value = _source()
    authorizer = MagicMock(spec=TenantAuthorizer)
    authorizer.require_context.return_value = TenantContext(
        ORGANIZATION_ID, UUID("80000000-0000-0000-0000-000000000001"), ACTOR_ID, "owner"
    )
    embedder = MagicMock(spec=EmbeddingProvider)
    embedder.embed_query.return_value = [1.0, 0.0]
    generator = MagicMock(spec=GenerationProvider)
    generator.generate.return_value = GenerationResult(
        parts=(GeneratedPart("Grounded answer", ("E1",)),), insufficient_context=False
    )
    telemetry = MagicMock(spec=RagTelemetry)
    service = RagService(
        repository,
        knowledge,
        authorizer,
        {"test": embedder},
        generator,
        telemetry,
        default_profile_key="local",
        minimum_vector_similarity=0.3,
        candidate_limit=5,
        evidence_limit=3,
        maximum_per_source=2,
    )
    return service, repository, knowledge, authorizer, embedder, generator, telemetry


def test_equal_weight_rrf_filters_vector_similarity_and_caps_sources() -> None:
    other_source = UUID("30000000-0000-0000-0000-000000000002")
    vector = [_candidate(1, vector=0.8), _candidate(2, vector=0.2), _candidate(3, vector=0.7)]
    lexical = [_candidate(3), _candidate(4), _candidate(5, source_id=other_source)]
    ranked = reciprocal_rank_fusion(
        vector, lexical, minimum_vector_similarity=0.3, limit=3, maximum_per_source=2
    )
    assert [item.candidate.chunk_id for item in ranked] == [
        vector[2].chunk_id,
        vector[0].chunk_id,
        lexical[2].chunk_id,
    ]
    assert [item.evidence_id for item in ranked] == ["E1", "E2", "E3"]


def test_enqueue_list_reindex_retry_and_profile_migration_lifecycle() -> None:
    service, repository, knowledge, authorizer, _, _, _ = _service()
    session = MagicMock(spec=AsyncSession)
    repository.ensure_settings_and_enqueue.return_value = (_generation(),)
    assert asyncio.run(
        service.enqueue_ready_source(session, actor_user_id=ACTOR_ID, source=_source())
    ) == (_generation(),)
    assert (
        asyncio.run(
            service.enqueue_ready_source(
                session, actor_user_id=ACTOR_ID, source=_source(status="processing")
            )
        )
        == ()
    )

    repository.list_generations.return_value = (_generation(),)
    assert asyncio.run(
        service.list_generations(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
        )
    ) == (_generation(),)

    repository.get_active_profile.return_value = None
    with pytest.raises(RagNotConfiguredError):
        asyncio.run(
            service.reindex(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                request_id=None,
            )
        )
    repository.get_active_profile.return_value = _profile()
    repository.enqueue_reindex.return_value = _generation()
    assert (
        asyncio.run(
            service.reindex(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                request_id=None,
            )
        )
        == _generation()
    )

    unknown_id = UUID("60000000-0000-0000-0000-000000000002")
    with pytest.raises(RagGenerationNotFoundError):
        asyncio.run(
            service.retry(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                generation_id=unknown_id,
            )
        )
    repository.retry_generation.return_value = None
    with pytest.raises(RagGenerationNotFoundError):
        asyncio.run(
            service.retry(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                generation_id=GENERATION_ID,
            )
        )
    repository.retry_generation.return_value = _generation()
    assert (
        asyncio.run(
            service.retry(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                generation_id=GENERATION_ID,
            )
        )
        == _generation()
    )

    repository.get_profile.return_value = None
    with pytest.raises(RagProfileNotFoundError):
        asyncio.run(
            service.migrate_profile(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                profile_key="missing",
                request_id=None,
            )
        )
    repository.get_profile.return_value = _profile()
    repository.begin_profile_migration.return_value = (_generation(),)
    assert asyncio.run(
        service.migrate_profile(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            profile_key="local",
            request_id=None,
        )
    ) == (_generation(),)
    assert authorizer.require_role.call_count == 7

    knowledge.get_source.return_value = None
    with pytest.raises(KnowledgeSourceNotFoundError):
        asyncio.run(
            service.list_generations(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
            )
        )


def test_answer_returns_citations_and_explicit_no_answer_states() -> None:
    service, repository, _, _, _, _, telemetry = _service()
    session = MagicMock(spec=AsyncSession)
    repository.get_active_profile.return_value = _profile()
    vector = _candidate(1, vector=0.9)
    repository.retrieve_vector.return_value = (vector,)
    repository.retrieve_lexical.return_value = (_candidate(1),)

    answer = asyncio.run(
        service.answer(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            question="How long?",
        )
    )
    assert answer.text == "Grounded answer"
    assert not answer.insufficient_context
    assert answer.citations[0].version_id == VERSION_ID
    assert (answer.citations[0].answer_start, answer.citations[0].answer_end) == (0, 15)
    telemetry.retrieval_completed.assert_called_once()

    repository.retrieve_vector.return_value = ()
    repository.retrieve_lexical.return_value = ()
    no_evidence = asyncio.run(
        service.answer(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            question="Unknown",
        )
    )
    assert no_evidence.text == INSUFFICIENT_CONTEXT_ANSWER
    assert no_evidence.insufficient_context


def test_answer_handles_configuration_provider_and_generation_failures() -> None:
    service, repository, _, _, embedder, _, _ = _service()
    session = MagicMock(spec=AsyncSession)
    repository.get_active_profile.return_value = None
    with pytest.raises(RagNotConfiguredError):
        asyncio.run(
            service.answer(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                question="Question",
            )
        )
    repository.get_active_profile.return_value = replace(_profile(), provider="missing")
    with pytest.raises(RagNotConfiguredError):
        asyncio.run(
            service.answer(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                question="Question",
            )
        )

    repository.get_active_profile.return_value = _profile()
    embedder.embed_query.side_effect = ProviderError("offline")
    with pytest.raises(RagProviderUnavailableError):
        asyncio.run(
            service.answer(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                question="Question",
            )
        )


def test_answer_handles_generator_no_answer_error_and_unknown_evidence() -> None:
    service, repository, _, _, _, generator, _ = _service()
    session = MagicMock(spec=AsyncSession)
    repository.get_active_profile.return_value = _profile()
    repository.retrieve_vector.return_value = (_candidate(1, vector=0.9),)
    repository.retrieve_lexical.return_value = ()
    generator.generate.return_value = GenerationResult(parts=(), insufficient_context=True)
    result = asyncio.run(
        service.answer(
            session,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            question="Question",
        )
    )
    assert result.insufficient_context

    generator.generate.side_effect = ProviderError("offline")
    with pytest.raises(RagProviderUnavailableError):
        asyncio.run(
            service.answer(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                question="Question",
            )
        )
    generator.generate.side_effect = None
    generator.generate.return_value = GenerationResult(
        parts=(GeneratedPart("Part one", ("E1",)), GeneratedPart("Part two", ("E404",))),
        insufficient_context=False,
    )
    with pytest.raises(RagProviderUnavailableError):
        asyncio.run(
            service.answer(
                session,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                question="Question",
            )
        )
