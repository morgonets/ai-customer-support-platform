import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.chunking import ReferenceChunker
from app.rag.models import Chunk, ChunkSet, ClaimedGeneration, EmbeddingProfile
from app.rag.repository import RagRepository, WorkerRagRepository, vector_literal

NOW = datetime(2026, 9, 9, tzinfo=UTC)
ORGANIZATION_ID = UUID("10000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("20000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("30000000-0000-0000-0000-000000000001")
PROFILE_ID = UUID("40000000-0000-0000-0000-000000000001")
STAGING_PROFILE_ID = UUID("40000000-0000-0000-0000-000000000002")
GENERATION_ID = UUID("50000000-0000-0000-0000-000000000001")
CHUNK_SET_ID = UUID("60000000-0000-0000-0000-000000000001")
CHUNK_ID = UUID("70000000-0000-0000-0000-000000000001")
ACTOR_ID = UUID("80000000-0000-0000-0000-000000000001")


class Result:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        scalar: object = None,
    ) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self) -> "Result":
        return self

    def one(self) -> dict[str, Any]:
        return self.rows[0]

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)

    def scalar_one(self) -> object:
        return self.scalar

    def scalar_one_or_none(self) -> object:
        return self.scalar


def _session(*results: Result) -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    session.execute.side_effect = list(results)
    return session


def _profile_row(profile_id: UUID = PROFILE_ID) -> dict[str, Any]:
    return {
        "id": profile_id,
        "profile_key": "local" if profile_id == PROFILE_ID else "staging",
        "provider": "deterministic",
        "model": "hash-v1",
        "model_revision": "1",
        "dimensions": 1536,
    }


def _generation_row(generation_id: UUID = GENERATION_ID) -> dict[str, Any]:
    return {
        "id": generation_id,
        "knowledge_source_version_id": VERSION_ID,
        "profile_key": "local",
        "generation_number": 1,
        "status": "queued",
        "is_active": False,
        "attempt_count": 0,
        "failure_code": None,
        "failure_message": None,
        "created_at": NOW,
        "completed_at": None,
    }


def _candidate_row(*, locator: object) -> dict[str, Any]:
    return {
        "chunk_id": CHUNK_ID,
        "source_id": SOURCE_ID,
        "version_id": VERSION_ID,
        "version_number": 1,
        "source_title": "Guide",
        "source_kind": "article",
        "content": "Evidence",
        "locator": locator,
        "vector_score": 0.9,
        "lexical_score": None,
    }


def test_vector_serialization_and_mapping_helpers() -> None:
    assert vector_literal([1, -0.5]) == "[1,-0.5]"
    with pytest.raises(ValueError, match="must not be empty"):
        vector_literal([])
    repository = RagRepository()
    assert repository._profile(_profile_row()).dimensions == 1536
    assert repository._generation(_generation_row()).id == GENERATION_ID
    assert repository._candidate(_candidate_row(locator={"page": 1})).locator == {"page": 1}
    assert repository._candidate(_candidate_row(locator='{"page":2}')).locator == {"page": 2}


def test_profile_generation_and_retry_reads() -> None:
    repository = RagRepository()
    session = _session(
        Result(),
        Result(rows=[_profile_row()]),
        Result(),
        Result(rows=[_profile_row()]),
        Result(rows=[_generation_row()]),
        Result(),
        Result(rows=[_generation_row()]),
    )
    assert asyncio.run(repository.get_profile(session, "missing")) is None
    assert asyncio.run(repository.get_profile(session, "local")) is not None
    assert asyncio.run(repository.get_active_profile(session, ORGANIZATION_ID)) is None
    assert asyncio.run(repository.get_active_profile(session, ORGANIZATION_ID)) is not None
    assert (
        asyncio.run(repository.list_generations(session, ORGANIZATION_ID, SOURCE_ID))[0].id
        == GENERATION_ID
    )
    assert asyncio.run(repository.retry_generation(session, ORGANIZATION_ID, GENERATION_ID)) is None
    assert (
        asyncio.run(repository.retry_generation(session, ORGANIZATION_ID, GENERATION_ID))
        is not None
    )


def test_ensure_settings_handles_missing_profile_and_existing_generations() -> None:
    repository = RagRepository()
    no_profile = _session(Result())
    assert (
        asyncio.run(
            repository.ensure_settings_and_enqueue(
                no_profile,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                version_id=VERSION_ID,
                actor_user_id=ACTOR_ID,
                profile_key="missing",
            )
        )
        == ()
    )

    existing = _session(
        Result(rows=[_profile_row()]),
        Result(),
        Result(rows=[{"active_profile_id": PROFILE_ID, "staging_profile_id": None}]),
        Result(),
        Result(rows=[_generation_row()]),
    )
    result = asyncio.run(
        repository.ensure_settings_and_enqueue(
            existing,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            actor_user_id=ACTOR_ID,
            profile_key="local",
        )
    )
    assert result[0].id == GENERATION_ID


def test_ensure_settings_enqueues_active_and_staging_profiles() -> None:
    repository = RagRepository()
    first_id = UUID("50000000-0000-0000-0000-000000000011")
    second_id = UUID("50000000-0000-0000-0000-000000000012")
    first_insert = {**_generation_row(first_id), "profile_key": "local"}
    second_insert = {**_generation_row(second_id), "profile_key": "staging"}
    session = _session(
        Result(rows=[_profile_row()]),
        Result(),
        Result(rows=[{"active_profile_id": PROFILE_ID, "staging_profile_id": STAGING_PROFILE_ID}]),
        Result(),
        Result(),
        Result(scalar=1),
        Result(rows=[first_insert]),
        Result(scalar="local"),
        Result(),
        Result(),
        Result(scalar=1),
        Result(rows=[second_insert]),
        Result(scalar="staging"),
    )
    generations = asyncio.run(
        repository.ensure_settings_and_enqueue(
            session,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            actor_user_id=ACTOR_ID,
            profile_key="local",
        )
    )
    assert {item.id for item in generations} == {first_id, second_id}


def test_explicit_reindex_and_profile_migration_paths() -> None:
    repository = RagRepository()
    reindex_session = _session(
        Result(),
        Result(scalar=2),
        Result(rows=[{**_generation_row(), "generation_number": 2}]),
        Result(scalar="local"),
    )
    assert (
        asyncio.run(
            repository.enqueue_reindex(
                reindex_session,
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                version_id=VERSION_ID,
                actor_user_id=ACTOR_ID,
                profile_id=PROFILE_ID,
                request_id=None,
            )
        ).generation_number
        == 2
    )

    assert (
        asyncio.run(
            repository.begin_profile_migration(
                _session(Result()),
                organization_id=ORGANIZATION_ID,
                actor_user_id=ACTOR_ID,
                profile_key="missing",
                request_id=None,
            )
        )
        == ()
    )
    no_change = _session(Result(rows=[_profile_row()]), Result())
    assert (
        asyncio.run(
            repository.begin_profile_migration(
                no_change,
                organization_id=ORGANIZATION_ID,
                actor_user_id=ACTOR_ID,
                profile_key="local",
                request_id=None,
            )
        )
        == ()
    )

    migration = _session(
        Result(rows=[_profile_row(STAGING_PROFILE_ID)]),
        Result(scalar=ORGANIZATION_ID),
        Result(rows=[{"source_id": SOURCE_ID, "version_id": VERSION_ID}]),
        Result(),
        Result(rows=[{**_generation_row(), "profile_key": "staging"}]),
    )
    assert (
        len(
            asyncio.run(
                repository.begin_profile_migration(
                    migration,
                    organization_id=ORGANIZATION_ID,
                    actor_user_id=ACTOR_ID,
                    profile_key="staging",
                    request_id=None,
                )
            )
        )
        == 1
    )


def test_exact_and_indexed_vector_and_lexical_retrieval() -> None:
    repository = RagRepository()
    exact = _session(Result(), Result(), Result(rows=[_candidate_row(locator={"page": 1})]))
    assert (
        len(
            asyncio.run(
                repository.retrieve_vector(
                    exact,
                    organization_id=ORGANIZATION_ID,
                    profile_id=PROFILE_ID,
                    query_vector=[1, 0],
                    limit=5,
                    exact=True,
                )
            )
        )
        == 1
    )
    indexed = _session(Result(rows=[_candidate_row(locator={"page": 1})]))
    assert (
        len(
            asyncio.run(
                repository.retrieve_vector(
                    indexed,
                    organization_id=ORGANIZATION_ID,
                    profile_id=PROFILE_ID,
                    query_vector=[1, 0],
                    limit=5,
                    exact=False,
                )
            )
        )
        == 1
    )
    lexical_row = {
        **_candidate_row(locator={"page": 1}),
        "vector_score": None,
        "lexical_score": 0.5,
    }
    assert (
        len(
            asyncio.run(
                repository.retrieve_lexical(
                    _session(Result(rows=[lexical_row])),
                    organization_id=ORGANIZATION_ID,
                    question="refund",
                    limit=5,
                )
            )
        )
        == 1
    )


def _claim_row(locator: object) -> dict[str, Any]:
    return {
        "generation_id": GENERATION_ID,
        "organization_id": ORGANIZATION_ID,
        "source_id": SOURCE_ID,
        "knowledge_source_version_id": VERSION_ID,
        "embedding_profile_id": PROFILE_ID,
        "profile_key": "local",
        "provider": "deterministic",
        "model": "hash-v1",
        "model_revision": "1",
        "dimensions": 2,
        "attempt_count": 1,
        "lease_token": UUID("90000000-0000-0000-0000-000000000001"),
        "normalized_text": "Evidence",
        "normalization_version": 1,
        "locator_map": locator,
    }


def _claimed() -> ClaimedGeneration:
    row = _claim_row({"schema_version": 1, "segments": []})
    return ClaimedGeneration(
        id=row["generation_id"],
        organization_id=row["organization_id"],
        source_id=row["source_id"],
        version_id=row["knowledge_source_version_id"],
        profile=EmbeddingProfile(PROFILE_ID, "local", "deterministic", "hash-v1", "1", 2),
        attempt_count=1,
        lease_token=row["lease_token"],
        normalized_text="Evidence",
        normalization_version=1,
        locator_map=row["locator_map"],
    )


def test_worker_repository_claim_artifacts_completion_and_failure() -> None:
    repository = WorkerRagRepository()
    assert (
        asyncio.run(repository.claim(_session(Result()), worker_id="worker", lease_seconds=30))
        is None
    )
    claimed = asyncio.run(
        repository.claim(
            _session(Result(rows=[_claim_row(json.dumps({"schema_version": 1}))]), Result()),
            worker_id="worker",
            lease_seconds=30,
        )
    )
    assert claimed is not None
    assert claimed.locator_map == {"schema_version": 1}
    claimed_with_mapping = asyncio.run(
        repository.claim(
            _session(Result(rows=[_claim_row({"schema_version": 1})]), Result()),
            worker_id="worker",
            lease_seconds=30,
        )
    )
    assert claimed_with_mapping is not None

    chunk_set = ChunkSet(
        id=CHUNK_SET_ID,
        fingerprint="a" * 64,
        normalized_content_sha256="b" * 64,
        chunks=(
            Chunk(
                id=CHUNK_ID,
                ordinal=0,
                content="Evidence",
                start_char=0,
                end_char=8,
                content_sha256="c" * 64,
                locator={"schema_version": 1},
            ),
        ),
    )
    artifact_session = _session(Result(), Result(), Result(), Result())
    asyncio.run(
        repository.replace_artifacts(
            artifact_session,
            generation=_claimed(),
            chunk_set=chunk_set,
            embeddings=[[1, 0]],
            chunker=ReferenceChunker(target_characters=10, overlap_characters=1),
        )
    )
    assert artifact_session.execute.await_count == 4
    assert asyncio.run(
        repository.complete(
            _session(Result(scalar=True)),
            generation=_claimed(),
            chunk_set_id=CHUNK_SET_ID,
            chunk_count=1,
            input_tokens=None,
        )
    )
    failure_session = _session(Result())
    asyncio.run(
        repository.fail(
            failure_session,
            generation=_claimed(),
            code="failed",
            message="safe",
            retry_at=NOW,
        )
    )
    failure_session.execute.assert_awaited_once()
