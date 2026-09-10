import argparse
import asyncio
import logging
import socket
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.rag.chunking import ReferenceChunker
from app.rag.models import ClaimedGeneration
from app.rag.ports import EmbeddingProvider, RagTelemetry
from app.rag.providers import (
    DeterministicEmbeddingProvider,
    LoggingRagTelemetry,
    OpenAIEmbeddingProvider,
    ProviderError,
    elapsed_milliseconds,
)
from app.rag.repository import WorkerRagRepository

logger = logging.getLogger("app.rag.worker")


class WorkerDatabase:
    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url, pool_pre_ping=True)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self, lease_token: str | None = None) -> AsyncIterator[AsyncSession]:
        async with self._sessions.begin() as session:
            await session.execute(text("set local role app_rag_worker"))
            if lease_token is not None:
                await session.execute(
                    text("select set_config('app.rag_lease_token', :lease_token, true)"),
                    {"lease_token": lease_token},
                )
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()


class IndexingWorker:
    def __init__(
        self,
        database: WorkerDatabase,
        repository: WorkerRagRepository,
        providers: Mapping[str, EmbeddingProvider],
        telemetry: RagTelemetry,
        *,
        worker_id: str,
        lease_seconds: int,
        maximum_attempts: int,
        retry_delay_seconds: int,
        chunker: ReferenceChunker | None = None,
    ) -> None:
        self._database = database
        self._repository = repository
        self._providers = providers
        self._telemetry = telemetry
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._maximum_attempts = maximum_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._chunker = chunker or ReferenceChunker()

    async def process_one(self) -> bool:
        async with self._database.session() as session:
            generation = await self._repository.claim(
                session, worker_id=self._worker_id, lease_seconds=self._lease_seconds
            )
        if generation is None:
            return False
        started = time.monotonic()
        provider = self._providers.get(generation.profile.provider)
        if provider is None:
            await self._mark_failure(generation, "provider_not_configured")
            return True
        try:
            chunk_set = self._chunker.chunk(
                organization_id=generation.organization_id,
                source_id=generation.source_id,
                version_id=generation.version_id,
                normalized_text=generation.normalized_text,
                normalization_version=generation.normalization_version,
                locator_map=generation.locator_map,
            )
            embeddings = await provider.embed_documents(
                [chunk.content for chunk in chunk_set.chunks],
                model=generation.profile.model,
                dimensions=generation.profile.dimensions,
            )
            if len(embeddings) != len(chunk_set.chunks):
                raise ProviderError("provider returned an invalid embedding count")
        except (ProviderError, ValueError) as exc:
            logger.error(
                "rag.indexing_failed",
                extra={
                    "error_type": type(exc).__name__,
                    "generation_id": str(generation.id),
                    "provider": generation.profile.provider,
                },
            )
            await self._mark_failure(generation, "indexing_failed")
            return True
        try:
            async with self._database.session(str(generation.lease_token)) as session:
                await self._repository.replace_artifacts(
                    session,
                    generation=generation,
                    chunk_set=chunk_set,
                    embeddings=embeddings,
                    chunker=self._chunker,
                )
                await self._repository.complete(
                    session,
                    generation=generation,
                    chunk_set_id=chunk_set.id,
                    chunk_count=len(chunk_set.chunks),
                    input_tokens=None,
                )
        except Exception as exc:
            logger.error(
                "rag.index_persistence_failed",
                extra={
                    "generation_id": str(generation.id),
                    "error_type": type(exc).__name__,
                },
            )
            await self._mark_failure(generation, "persistence_failed")
            return True
        self._telemetry.indexing_completed(
            provider=generation.profile.provider,
            chunk_count=len(chunk_set.chunks),
            elapsed_ms=elapsed_milliseconds(started),
        )
        return True

    async def _mark_failure(self, generation: ClaimedGeneration, code: str) -> None:
        retry_at = None
        if (
            generation.profile.provider in self._providers
            and generation.attempt_count < self._maximum_attempts
        ):
            retry_at = datetime.now(tz=UTC) + timedelta(seconds=self._retry_delay_seconds)
        try:
            async with self._database.session(str(generation.lease_token)) as session:
                await self._repository.fail(
                    session,
                    generation=generation,
                    code=code,
                    message=(
                        "Indexing did not complete; the previous active generation remains "
                        "available."
                    ),
                    retry_at=retry_at,
                )
        except Exception as exc:
            # Deletion or another worker reclaiming an expired lease makes this update stale.
            # The durable row is already absent or owned by the new worker, so fail closed.
            logger.error(
                "rag.failure_state_not_recorded",
                extra={
                    "generation_id": str(generation.id),
                    "error_type": type(exc).__name__,
                },
            )


async def run_worker(*, once: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = WorkerDatabase(settings.rag_worker_database_url)
    providers: dict[str, EmbeddingProvider] = {"deterministic": DeterministicEmbeddingProvider()}
    if settings.openai_api_key:
        providers["openai"] = OpenAIEmbeddingProvider(
            settings.openai_api_key.get_secret_value(), base_url=settings.openai_api_base_url
        )
    worker = IndexingWorker(
        database,
        WorkerRagRepository(),
        providers,
        LoggingRagTelemetry(),
        worker_id=f"{socket.gethostname()}:{id(database)}",
        lease_seconds=settings.rag_worker_lease_seconds,
        maximum_attempts=settings.rag_worker_maximum_attempts,
        retry_delay_seconds=settings.rag_worker_retry_delay_seconds,
    )
    try:
        while True:
            worked = await worker.process_one()
            if once:
                return
            if not worked:
                await asyncio.sleep(settings.rag_worker_poll_seconds)
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process durable RAG indexing generations")
    parser.add_argument("--once", action="store_true", help="claim at most one generation")
    arguments = parser.parse_args()
    asyncio.run(run_worker(once=arguments.once))


if __name__ == "__main__":  # pragma: no cover - exercised through main().
    main()
