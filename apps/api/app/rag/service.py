import time
from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import KnowledgeSourceNotFoundError
from app.knowledge.models import KnowledgeSource
from app.knowledge.repository import KnowledgeRepository
from app.rag.errors import (
    RagGenerationNotFoundError,
    RagNotConfiguredError,
    RagProfileNotFoundError,
    RagProviderUnavailableError,
)
from app.rag.models import Answer, Citation, IndexGeneration, RankedEvidence, RetrievalCandidate
from app.rag.ports import EmbeddingProvider, GenerationProvider, RagTelemetry
from app.rag.providers import ProviderError, elapsed_milliseconds
from app.rag.repository import RagRepository
from app.tenants.authorization import TenantAuthorizer

RRF_K = 60
INSUFFICIENT_CONTEXT_ANSWER = "I don't have enough information in the knowledge base to answer."


def reciprocal_rank_fusion(
    vector: Sequence[RetrievalCandidate],
    lexical: Sequence[RetrievalCandidate],
    *,
    minimum_vector_similarity: float,
    limit: int,
    maximum_per_source: int,
) -> tuple[RankedEvidence, ...]:
    candidates: dict[UUID, RetrievalCandidate] = {}
    scores: dict[UUID, float] = {}
    for rank, item in enumerate(vector, start=1):
        if item.vector_score is not None and item.vector_score >= minimum_vector_similarity:
            candidates[item.chunk_id] = item
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1 / (RRF_K + rank)
    for rank, item in enumerate(lexical, start=1):
        candidates.setdefault(item.chunk_id, item)
        scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + 1 / (RRF_K + rank)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], str(chunk_id)))
    counts: dict[UUID, int] = {}
    selected: list[RankedEvidence] = []
    for chunk_id in ordered:
        candidate = candidates[chunk_id]
        source_count = counts.get(candidate.source_id, 0)
        if source_count >= maximum_per_source:
            continue
        selected.append(
            RankedEvidence(
                evidence_id=f"E{len(selected) + 1}",
                candidate=candidate,
                score=scores[chunk_id],
            )
        )
        counts[candidate.source_id] = source_count + 1
        if len(selected) == limit:
            break
    return tuple(selected)


class RagService:
    def __init__(
        self,
        repository: RagRepository,
        knowledge_repository: KnowledgeRepository,
        authorizer: TenantAuthorizer,
        embedding_providers: Mapping[str, EmbeddingProvider],
        generation_provider: GenerationProvider,
        telemetry: RagTelemetry,
        *,
        default_profile_key: str,
        minimum_vector_similarity: float,
        candidate_limit: int,
        evidence_limit: int,
        maximum_per_source: int,
        exact_vector_search: bool = True,
    ) -> None:
        self._repository = repository
        self._knowledge_repository = knowledge_repository
        self._authorizer = authorizer
        self._embedding_providers = embedding_providers
        self._generation_provider = generation_provider
        self._telemetry = telemetry
        self._default_profile_key = default_profile_key
        self._minimum_vector_similarity = minimum_vector_similarity
        self._candidate_limit = candidate_limit
        self._evidence_limit = evidence_limit
        self._maximum_per_source = maximum_per_source
        self._exact_vector_search = exact_vector_search

    async def enqueue_ready_source(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        source: KnowledgeSource,
        request_id: UUID | None = None,
    ) -> tuple[IndexGeneration, ...]:
        if source.current_version.status != "ready":
            return ()
        return await self._repository.ensure_settings_and_enqueue(
            session,
            organization_id=source.organization_id,
            source_id=source.id,
            version_id=source.current_version.id,
            actor_user_id=actor_user_id,
            profile_key=self._default_profile_key,
            request_id=request_id,
        )

    async def list_generations(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> tuple[IndexGeneration, ...]:
        await self._require_source(session, actor_user_id, organization_id, source_id)
        return await self._repository.list_generations(session, organization_id, source_id)

    async def reindex(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        request_id: UUID | None,
    ) -> IndexGeneration:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        source = await self._required_source(session, organization_id, source_id)
        profile = await self._repository.get_active_profile(session, organization_id)
        if profile is None:
            generations = await self._repository.ensure_settings_and_enqueue(
                session,
                organization_id=organization_id,
                source_id=source.id,
                version_id=source.current_version.id,
                actor_user_id=actor_user_id,
                profile_key=self._default_profile_key,
                request_id=request_id,
            )
            if not generations:
                raise RagNotConfiguredError
            return generations[0]
        return await self._repository.enqueue_reindex(
            session,
            organization_id=organization_id,
            source_id=source.id,
            version_id=source.current_version.id,
            actor_user_id=actor_user_id,
            profile_id=profile.id,
            request_id=request_id,
        )

    async def retry(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        generation_id: UUID,
    ) -> IndexGeneration:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        await self._required_source(session, organization_id, source_id)
        generations = await self._repository.list_generations(session, organization_id, source_id)
        if not any(item.id == generation_id for item in generations):
            raise RagGenerationNotFoundError
        generation = await self._repository.retry_generation(
            session, organization_id, generation_id
        )
        if generation is None:
            raise RagGenerationNotFoundError
        return generation

    async def migrate_profile(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        profile_key: str,
        request_id: UUID | None,
    ) -> tuple[IndexGeneration, ...]:
        context = await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        self._authorizer.require_role(context, "owner", "admin")
        profile = await self._repository.get_profile(session, profile_key)
        if profile is None:
            raise RagProfileNotFoundError
        return await self._repository.begin_profile_migration(
            session,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            profile_key=profile.profile_key,
            request_id=request_id,
        )

    async def answer(
        self,
        session: AsyncSession,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        question: str,
    ) -> Answer:
        await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        profile = await self._repository.get_active_profile(session, organization_id)
        if profile is None:
            raise RagNotConfiguredError
        provider = self._embedding_providers.get(profile.provider)
        if provider is None:
            raise RagNotConfiguredError
        started = time.monotonic()
        try:
            query_vector = await provider.embed_query(
                question, model=profile.model, dimensions=profile.dimensions
            )
            vector = await self._repository.retrieve_vector(
                session,
                organization_id=organization_id,
                profile_id=profile.id,
                query_vector=query_vector,
                limit=self._candidate_limit,
                exact=self._exact_vector_search,
            )
            lexical = await self._repository.retrieve_lexical(
                session,
                organization_id=organization_id,
                question=question,
                limit=self._candidate_limit,
            )
        except ProviderError as exc:
            raise RagProviderUnavailableError from exc
        evidence = reciprocal_rank_fusion(
            vector,
            lexical,
            minimum_vector_similarity=self._minimum_vector_similarity,
            limit=self._evidence_limit,
            maximum_per_source=self._maximum_per_source,
        )
        self._telemetry.retrieval_completed(
            vector_candidates=len(vector),
            lexical_candidates=len(lexical),
            selected=len(evidence),
            elapsed_ms=elapsed_milliseconds(started),
        )
        if not evidence:
            answer = Answer(
                text=INSUFFICIENT_CONTEXT_ANSWER, insufficient_context=True, citations=()
            )
            self._record_answer(started, answer)
            return answer
        try:
            generated = await self._generation_provider.generate(question, evidence)
        except ProviderError as exc:
            raise RagProviderUnavailableError from exc
        if generated.insufficient_context:
            answer = Answer(
                text=INSUFFICIENT_CONTEXT_ANSWER, insufficient_context=True, citations=()
            )
            self._record_answer(started, answer)
            return answer
        if not generated.parts or any(
            not part.text.strip() or not part.evidence_ids for part in generated.parts
        ):
            raise RagProviderUnavailableError
        evidence_by_id = {item.evidence_id: item for item in evidence}
        text_parts: list[str] = []
        citations: list[Citation] = []
        offset = 0
        for part in generated.parts:
            if text_parts:
                offset += 1
            start = offset
            text_parts.append(part.text)
            offset += len(part.text)
            for evidence_id in part.evidence_ids:
                item = evidence_by_id.get(evidence_id)
                if item is None:
                    raise RagProviderUnavailableError
                candidate = item.candidate
                citations.append(
                    Citation(
                        source_id=candidate.source_id,
                        version_id=candidate.version_id,
                        version_number=candidate.version_number,
                        source_title=candidate.source_title,
                        source_kind=candidate.source_kind,
                        locator=candidate.locator,
                        excerpt=" ".join(candidate.content.split())[:400],
                        answer_start=start,
                        answer_end=offset,
                    )
                )
        answer = Answer(
            text=" ".join(text_parts), insufficient_context=False, citations=tuple(citations)
        )
        self._record_answer(started, answer)
        return answer

    async def _require_source(
        self, session: AsyncSession, actor_user_id: UUID, organization_id: UUID, source_id: UUID
    ) -> KnowledgeSource:
        await self._authorizer.require_context(
            session, actor_user_id=actor_user_id, organization_id=organization_id
        )
        return await self._required_source(session, organization_id, source_id)

    async def _required_source(
        self, session: AsyncSession, organization_id: UUID, source_id: UUID
    ) -> KnowledgeSource:
        source = await self._knowledge_repository.get_source(session, organization_id, source_id)
        if source is None:
            raise KnowledgeSourceNotFoundError
        return source

    def _record_answer(self, started: float, answer: Answer) -> None:
        self._telemetry.answer_completed(
            insufficient_context=answer.insufficient_context,
            citation_count=len(answer.citations),
            elapsed_ms=elapsed_milliseconds(started),
        )
