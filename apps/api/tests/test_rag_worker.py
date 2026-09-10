import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.models import ClaimedGeneration, EmbeddingProfile
from app.rag.ports import EmbeddingProvider, RagTelemetry
from app.rag.providers import ProviderError
from app.rag.repository import WorkerRagRepository
from app.rag.worker import IndexingWorker, WorkerDatabase, main, run_worker


def _generation(*, provider: str = "deterministic", attempts: int = 1) -> ClaimedGeneration:
    return ClaimedGeneration(
        id=UUID("10000000-0000-0000-0000-000000000001"),
        organization_id=UUID("20000000-0000-0000-0000-000000000001"),
        source_id=UUID("30000000-0000-0000-0000-000000000001"),
        version_id=UUID("40000000-0000-0000-0000-000000000001"),
        profile=EmbeddingProfile(
            UUID("50000000-0000-0000-0000-000000000001"),
            "local",
            provider,
            "hash-v1",
            "1",
            2,
        ),
        attempt_count=attempts,
        lease_token=UUID("60000000-0000-0000-0000-000000000001"),
        normalized_text="Grounded evidence",
        normalization_version=1,
        locator_map={
            "schema_version": 1,
            "segments": [{"kind": "text", "start": 0, "end": 17}],
        },
    )


class FakeDatabase:
    def __init__(self) -> None:
        self.sessions: list[MagicMock] = []
        self.tokens: list[str | None] = []

    @asynccontextmanager
    async def session(self, lease_token: str | None = None) -> AsyncIterator[AsyncSession]:
        session = MagicMock(spec=AsyncSession)
        self.sessions.append(session)
        self.tokens.append(lease_token)
        yield cast(AsyncSession, session)


def _worker(
    database: FakeDatabase,
    repository: MagicMock,
    provider: MagicMock | None,
    *,
    attempts: int = 1,
) -> IndexingWorker:
    del attempts
    providers = {} if provider is None else {"deterministic": cast(EmbeddingProvider, provider)}
    return IndexingWorker(
        cast(WorkerDatabase, database),
        cast(WorkerRagRepository, repository),
        providers,
        cast(RagTelemetry, MagicMock(spec=RagTelemetry)),
        worker_id="worker",
        lease_seconds=60,
        maximum_attempts=3,
        retry_delay_seconds=5,
    )


def test_worker_returns_false_when_the_queue_is_empty() -> None:
    database = FakeDatabase()
    repository = MagicMock(spec=WorkerRagRepository)
    repository.claim.return_value = None
    assert not asyncio.run(_worker(database, repository, None).process_one())
    assert database.tokens == [None]


def test_worker_builds_and_completes_a_generation() -> None:
    database = FakeDatabase()
    repository = MagicMock(spec=WorkerRagRepository)
    repository.claim.return_value = _generation()
    repository.complete.return_value = True
    provider = MagicMock(spec=EmbeddingProvider)
    provider.embed_documents.return_value = [[1.0, 0.0]]
    telemetry = MagicMock(spec=RagTelemetry)
    worker = IndexingWorker(
        cast(WorkerDatabase, database),
        cast(WorkerRagRepository, repository),
        {"deterministic": cast(EmbeddingProvider, provider)},
        cast(RagTelemetry, telemetry),
        worker_id="worker",
        lease_seconds=60,
        maximum_attempts=3,
        retry_delay_seconds=5,
    )
    assert asyncio.run(worker.process_one())
    repository.replace_artifacts.assert_awaited_once()
    repository.complete.assert_awaited_once()
    telemetry.indexing_completed.assert_called_once()
    assert database.tokens == [None, str(_generation().lease_token)]


@pytest.mark.parametrize("failure", [ProviderError("offline"), ValueError("bad chunks")])
def test_worker_retries_safe_provider_or_chunking_failures(failure: Exception) -> None:
    database = FakeDatabase()
    repository = MagicMock(spec=WorkerRagRepository)
    repository.claim.return_value = _generation()
    provider = MagicMock(spec=EmbeddingProvider)
    provider.embed_documents.side_effect = failure
    assert asyncio.run(_worker(database, repository, provider).process_one())
    assert repository.fail.await_args.kwargs["retry_at"] is not None
    assert repository.fail.await_args.kwargs["code"] == "indexing_failed"


def test_worker_rejects_wrong_embedding_count_and_stops_retrying_at_limit() -> None:
    database = FakeDatabase()
    repository = MagicMock(spec=WorkerRagRepository)
    repository.claim.return_value = _generation(attempts=3)
    provider = MagicMock(spec=EmbeddingProvider)
    provider.embed_documents.return_value = []
    assert asyncio.run(_worker(database, repository, provider).process_one())
    assert repository.fail.await_args.kwargs["retry_at"] is None


def test_worker_marks_missing_provider_and_persistence_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    missing_database = FakeDatabase()
    missing_repository = MagicMock(spec=WorkerRagRepository)
    missing_repository.claim.return_value = _generation(provider="missing")
    assert asyncio.run(_worker(missing_database, missing_repository, None).process_one())
    assert missing_repository.fail.await_args.kwargs["code"] == "provider_not_configured"
    assert missing_repository.fail.await_args.kwargs["retry_at"] is None

    failed_database = FakeDatabase()
    failed_repository = MagicMock(spec=WorkerRagRepository)
    failed_repository.claim.return_value = _generation()
    failed_repository.replace_artifacts.side_effect = RuntimeError("private customer content")
    provider = MagicMock(spec=EmbeddingProvider)
    provider.embed_documents.return_value = [[1.0, 0.0]]
    assert asyncio.run(_worker(failed_database, failed_repository, provider).process_one())
    assert failed_repository.fail.await_args.kwargs["code"] == "persistence_failed"
    assert "private customer content" not in caplog.text

    stale_repository = MagicMock(spec=WorkerRagRepository)
    stale_repository.claim.return_value = _generation(provider="missing")
    stale_repository.fail.side_effect = RuntimeError("stale lease private detail")
    assert asyncio.run(_worker(FakeDatabase(), stale_repository, None).process_one())
    assert "stale lease private detail" not in caplog.text


def test_worker_database_sets_restricted_role_and_optional_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock(spec=AsyncSession)

    class Transaction:
        async def __aenter__(self) -> AsyncSession:
            return cast(AsyncSession, session)

        async def __aexit__(self, *args: object) -> None:
            return None

    sessions = MagicMock()
    sessions.begin.return_value = Transaction()
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr("app.rag.worker.create_async_engine", MagicMock(return_value=engine))
    monkeypatch.setattr("app.rag.worker.async_sessionmaker", MagicMock(return_value=sessions))
    database = WorkerDatabase("postgresql+psycopg://test")

    async def exercise() -> None:
        async with database.session():
            pass
        async with database.session("lease"):
            pass
        await database.dispose()

    asyncio.run(exercise())
    assert session.execute.await_count == 3
    engine.dispose.assert_awaited_once()


def test_run_worker_once_and_cli_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    database = MagicMock(spec=WorkerDatabase)
    database.dispose.return_value = None
    worker = MagicMock(spec=IndexingWorker)
    worker.process_one.return_value = False
    settings: Any = SimpleNamespace(
        rag_worker_database_url="postgresql+psycopg://test",
        openai_api_key=None,
        openai_api_base_url="https://api.openai.com/v1",
        rag_worker_lease_seconds=60,
        rag_worker_maximum_attempts=3,
        rag_worker_retry_delay_seconds=5,
        rag_worker_poll_seconds=1,
        log_level="INFO",
    )
    monkeypatch.setattr("app.rag.worker.get_settings", MagicMock(return_value=settings))
    monkeypatch.setattr("app.rag.worker.WorkerDatabase", MagicMock(return_value=database))
    monkeypatch.setattr("app.rag.worker.IndexingWorker", MagicMock(return_value=worker))
    configure_logging = MagicMock()
    monkeypatch.setattr("app.rag.worker.configure_logging", configure_logging)
    asyncio.run(run_worker(once=True))
    configure_logging.assert_called_with("INFO")
    database.dispose.assert_awaited_once()

    settings.openai_api_key = SecretStr("test-key")
    asyncio.run(run_worker(once=True))

    sleeper = AsyncMock(side_effect=RuntimeError("stop loop"))
    monkeypatch.setattr("app.rag.worker.asyncio.sleep", sleeper)
    worker.process_one.side_effect = [True, False]
    with pytest.raises(RuntimeError, match="stop loop"):
        asyncio.run(run_worker(once=False))
    sleeper.assert_awaited_once_with(1)

    def close_coroutine(coroutine: Coroutine[object, object, object]) -> None:
        coroutine.close()

    run = MagicMock(side_effect=close_coroutine)
    monkeypatch.setattr("app.rag.worker.asyncio.run", run)
    monkeypatch.setattr("sys.argv", ["rag-worker", "--once"])
    main()
    run.assert_called_once()
