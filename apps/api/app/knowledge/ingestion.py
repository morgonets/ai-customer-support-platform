import logging
import os
import tempfile
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from uuid import UUID

from anyio import to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.errors import (
    DocumentExtractionError,
    KnowledgeStorageUnavailableError,
)
from app.knowledge.extraction import AsyncUpload, DocumentExtractor, stage_upload
from app.knowledge.models import KnowledgeSource, ValidatedUpload
from app.knowledge.service import KnowledgeService
from app.knowledge.storage import ObjectStorage

logger = logging.getLogger("app.knowledge.ingestion")
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
ReadyCallback = Callable[[AsyncSession, UUID, KnowledgeSource], Awaitable[None]]


def _unlink(path: Path) -> None:
    path.unlink(missing_ok=True)


class KnowledgeIngestionCoordinator:
    def __init__(
        self,
        service: KnowledgeService,
        storage: ObjectStorage,
        extractor: DocumentExtractor,
        *,
        maximum_upload_bytes: int,
        processing_stale_seconds: int,
        ready_callback: ReadyCallback | None = None,
    ) -> None:
        self._service = service
        self._storage = storage
        self._extractor = extractor
        self._maximum_upload_bytes = maximum_upload_bytes
        self._processing_stale_seconds = processing_stale_seconds
        self._ready_callback = ready_callback

    async def create_document(
        self,
        session_factory: SessionFactory,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        title: str,
        description: str | None,
        upload: AsyncUpload,
    ) -> KnowledgeSource:
        validated = await stage_upload(upload, maximum_bytes=self._maximum_upload_bytes)
        temporary_path = Path(validated.temporary_path)
        try:
            async with session_factory() as session:
                source, file_object = await self._service.create_document_processing(
                    session,
                    actor_user_id=actor_user_id,
                    organization_id=organization_id,
                    title=title,
                    description=description,
                    original_filename=validated.original_filename,
                    media_type=validated.media_type,
                    size_bytes=validated.size_bytes,
                    sha256=validated.sha256,
                )
            try:
                await self._storage.put(file_object.storage_key, temporary_path)
            except KnowledgeStorageUnavailableError:
                return await self._mark_failure(
                    session_factory,
                    actor_user_id=actor_user_id,
                    organization_id=organization_id,
                    source_id=source.id,
                    code="storage_write_failed",
                    message="The original document could not be stored.",
                )
            return await self._extract_and_finish(
                session_factory,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source.id,
                temporary_path=temporary_path,
            )
        finally:
            await to_thread.run_sync(_unlink, temporary_path)

    async def retry_document(
        self,
        session_factory: SessionFactory,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> KnowledgeSource:
        async with session_factory() as session:
            _, file_object = await self._service.begin_document_retry(
                session,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
                stale_after_seconds=self._processing_stale_seconds,
            )
        descriptor, temporary_name = tempfile.mkstemp(prefix="knowledge-retry-")
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            try:
                await self._storage.copy_to(file_object.storage_key, temporary_path)
            except KnowledgeStorageUnavailableError:
                return await self._mark_failure(
                    session_factory,
                    actor_user_id=actor_user_id,
                    organization_id=organization_id,
                    source_id=source_id,
                    code="storage_read_failed",
                    message="The original document could not be read from storage.",
                )
            return await self._extract_and_finish(
                session_factory,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
                temporary_path=temporary_path,
            )
        finally:
            await to_thread.run_sync(_unlink, temporary_path)

    async def delete_source(
        self,
        session_factory: SessionFactory,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
    ) -> None:
        async with session_factory() as session:
            plan = await self._service.prepare_deletion(
                session,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
            )
        for file_object in plan.file_objects:
            await self._storage.delete(file_object.storage_key)
        async with session_factory() as session:
            await self._service.delete_source(
                session,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
            )

    async def _extract_and_finish(
        self,
        session_factory: SessionFactory,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        temporary_path: Path,
    ) -> KnowledgeSource:
        # Extraction needs only the persisted path and MIME type. The other immutable metadata is
        # not consulted by extractors, so this internal value cannot diverge from public metadata.
        async with session_factory() as session:
            source = await self._service.get_source(
                session,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
            )
        version = source.current_version
        if version.original_filename is None or version.media_type is None:
            raise RuntimeError("processing document metadata is incomplete")
        upload = ValidatedUpload(
            temporary_path=str(temporary_path),
            original_filename=version.original_filename,
            media_type=version.media_type,
            size_bytes=version.size_bytes or 0,
            sha256=version.sha256 or "",
        )
        try:
            extracted = await self._extractor.extract(upload)
        except DocumentExtractionError as exc:
            return await self._mark_failure(
                session_factory,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
                code=exc.code,
                message=exc.safe_message,
            )
        except Exception:
            logger.exception(
                "knowledge.extraction_failed",
                extra={
                    "organization_id": str(organization_id),
                    "source_id": str(source_id),
                },
            )
            return await self._mark_failure(
                session_factory,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
                code="text_extraction_failed",
                message="The document text could not be extracted.",
            )
        async with session_factory() as session:
            ready = await self._service.mark_document_ready(
                session,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
                extracted=extracted,
            )
            if self._ready_callback is not None:
                await self._ready_callback(session, actor_user_id, ready)
            return ready

    async def _mark_failure(
        self,
        session_factory: SessionFactory,
        *,
        actor_user_id: UUID,
        organization_id: UUID,
        source_id: UUID,
        code: str,
        message: str,
    ) -> KnowledgeSource:
        async with session_factory() as session:
            return await self._service.mark_document_failed(
                session,
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                source_id=source_id,
                failure_code=code,
                failure_message=message,
            )
