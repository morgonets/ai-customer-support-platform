import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import DocumentExtractionError, KnowledgeStorageUnavailableError
from app.knowledge.extraction import DocumentExtractor
from app.knowledge.ingestion import KnowledgeIngestionCoordinator
from app.knowledge.models import (
    ExtractedContent,
    KnowledgeDeletionPlan,
    KnowledgeFileObject,
    KnowledgeProcessingStatus,
    KnowledgeSource,
    KnowledgeSourceVersion,
)
from app.knowledge.service import KnowledgeService
from app.knowledge.storage import ObjectStorage

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
ACTOR_ID = UUID("10000000-0000-0000-0000-000000000001")
ORGANIZATION_ID = UUID("20000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("40000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("50000000-0000-0000-0000-000000000001")


class FakeUpload:
    filename: str | None = "guide.txt"
    content_type: str | None = "text/plain"

    def __init__(self) -> None:
        self._content = b"Knowledge content"

    async def read(self, size: int = -1) -> bytes:
        content, self._content = self._content[:size], self._content[size:]
        return content


def _source(status: str) -> KnowledgeSource:
    return KnowledgeSource(
        id=SOURCE_ID,
        organization_id=ORGANIZATION_ID,
        kind="document",
        title="Guide",
        description=None,
        created_by_user_id=ACTOR_ID,
        updated_by_user_id=ACTOR_ID,
        created_at=NOW,
        updated_at=NOW,
        current_version=KnowledgeSourceVersion(
            id=VERSION_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            kind="document",
            version_number=1,
            is_current=True,
            status=cast(KnowledgeProcessingStatus, status),
            raw_text=None,
            normalized_text="Knowledge content" if status == "ready" else None,
            normalization_version=1,
            locator_map={"schema_version": 1} if status == "ready" else None,
            original_filename="guide.txt",
            media_type="text/plain",
            size_bytes=17,
            sha256="a" * 64,
            extractor_name="plain_text" if status == "ready" else None,
            extractor_version="1" if status == "ready" else None,
            processing_attempts=1,
            processing_started_at=NOW,
            processed_at=NOW if status != "processing" else None,
            failure_code="failed" if status == "failed" else None,
            failure_message="Failed" if status == "failed" else None,
            created_by_user_id=ACTOR_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
    )


def _file() -> KnowledgeFileObject:
    return KnowledgeFileObject(
        version_id=VERSION_ID,
        storage_key=f"{ORGANIZATION_ID}/{SOURCE_ID}/{VERSION_ID}/content",
        original_filename="guide.txt",
        media_type="text/plain",
        size_bytes=17,
    )


def _coordinator(
    ready_callback: AsyncMock | None = None,
) -> tuple[KnowledgeIngestionCoordinator, MagicMock, MagicMock, MagicMock]:
    service_mock = MagicMock(spec=KnowledgeService)
    storage_mock = MagicMock(spec=ObjectStorage)
    extractor_mock = MagicMock(spec=DocumentExtractor)
    coordinator = KnowledgeIngestionCoordinator(
        cast(KnowledgeService, service_mock),
        cast(ObjectStorage, storage_mock),
        cast(DocumentExtractor, extractor_mock),
        maximum_upload_bytes=1024,
        processing_stale_seconds=900,
        ready_callback=ready_callback,
    )
    return coordinator, service_mock, storage_mock, extractor_mock


@asynccontextmanager
async def _sessions() -> AsyncIterator[AsyncSession]:
    yield AsyncMock(spec=AsyncSession)


def test_create_document_stores_extracts_and_marks_ready() -> None:
    ready_callback = AsyncMock()
    coordinator, service_mock, storage_mock, extractor_mock = _coordinator(ready_callback)
    service_mock.create_document_processing.return_value = (_source("processing"), _file())
    service_mock.get_source.return_value = _source("processing")
    extracted = ExtractedContent("Knowledge content", {"schema_version": 1}, "plain_text", "1")
    extractor_mock.extract.return_value = extracted
    service_mock.mark_document_ready.return_value = _source("ready")

    created = asyncio.run(
        coordinator.create_document(
            _sessions,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            title="Guide",
            description=None,
            upload=FakeUpload(),
        )
    )

    assert created.current_version.status == "ready"
    storage_mock.put.assert_awaited_once()
    extractor_mock.extract.assert_awaited_once()
    service_mock.mark_document_ready.assert_awaited_once()
    ready_callback.assert_awaited_once()


def test_create_document_persists_storage_and_extraction_failures() -> None:
    for failure, code in [
        (KnowledgeStorageUnavailableError(), "storage_write_failed"),
        (DocumentExtractionError("invalid_document", "Invalid document."), "invalid_document"),
        (RuntimeError("parser crashed"), "text_extraction_failed"),
    ]:
        coordinator, service_mock, storage_mock, extractor_mock = _coordinator()
        service_mock.create_document_processing.return_value = (_source("processing"), _file())
        service_mock.get_source.return_value = _source("processing")
        service_mock.mark_document_failed.return_value = _source("failed")
        if isinstance(failure, KnowledgeStorageUnavailableError):
            storage_mock.put.side_effect = failure
        else:
            extractor_mock.extract.side_effect = failure

        result = asyncio.run(
            coordinator.create_document(
                _sessions,
                actor_user_id=ACTOR_ID,
                organization_id=ORGANIZATION_ID,
                title="Guide",
                description=None,
                upload=FakeUpload(),
            )
        )

        assert result.current_version.status == "failed"
        assert service_mock.mark_document_failed.await_args.kwargs["failure_code"] == code


def test_retry_reads_stored_file_and_handles_storage_failure() -> None:
    coordinator, service_mock, storage_mock, extractor_mock = _coordinator()
    service_mock.begin_document_retry.return_value = (_source("processing"), _file())
    service_mock.get_source.return_value = _source("processing")
    extractor_mock.extract.return_value = ExtractedContent(
        "Knowledge", {"schema_version": 1}, "plain_text", "1"
    )
    service_mock.mark_document_ready.return_value = _source("ready")

    async def copy_content(key: str, destination: Path) -> None:
        assert key == _file().storage_key
        assert destination.name

    storage_mock.copy_to.side_effect = copy_content
    retried = asyncio.run(
        coordinator.retry_document(
            _sessions,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
        )
    )
    assert retried.current_version.status == "ready"

    failed_coordinator, failed_service, failed_storage, _ = _coordinator()
    failed_service.begin_document_retry.return_value = (_source("processing"), _file())
    failed_service.mark_document_failed.return_value = _source("failed")
    failed_storage.copy_to.side_effect = KnowledgeStorageUnavailableError
    failed = asyncio.run(
        failed_coordinator.retry_document(
            _sessions,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
        )
    )
    assert failed.current_version.status == "failed"
    assert failed_service.mark_document_failed.await_args.kwargs["failure_code"] == (
        "storage_read_failed"
    )


def test_delete_removes_files_before_database_source() -> None:
    coordinator, service_mock, storage_mock, _ = _coordinator()
    service_mock.prepare_deletion.return_value = KnowledgeDeletionPlan(
        source=_source("ready"), file_objects=[_file()]
    )

    asyncio.run(
        coordinator.delete_source(
            _sessions,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
        )
    )

    storage_mock.delete.assert_awaited_once_with(_file().storage_key)
    service_mock.delete_source.assert_awaited_once()


def test_processing_requires_persisted_file_metadata() -> None:
    coordinator, service_mock, _, _ = _coordinator()
    source = _source("processing")
    incomplete_version = replace(source.current_version, original_filename=None)
    service_mock.get_source.return_value = replace(source, current_version=incomplete_version)

    async def exercise() -> None:
        await coordinator._extract_and_finish(
            _sessions,
            actor_user_id=ACTOR_ID,
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            temporary_path=Path("unused"),
        )

    with pytest.raises(RuntimeError, match="metadata is incomplete"):
        asyncio.run(exercise())
