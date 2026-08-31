from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Annotated, Any, BinaryIO
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentActor, CurrentDatabase, CurrentSession
from app.core.config import get_settings
from app.knowledge.errors import KnowledgeInvalidDocumentError
from app.knowledge.extraction import DocumentExtractor, default_document_title, safe_upload_filename
from app.knowledge.ingestion import KnowledgeIngestionCoordinator
from app.knowledge.models import (
    KnowledgeProcessingStatus,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceVersion,
)
from app.knowledge.normalization import MAX_ARTICLE_CHARACTERS
from app.knowledge.repository import SqlAlchemyKnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.knowledge.storage import ObjectStorage
from app.tenants.authorization import TenantAuthorizer
from app.tenants.repository import SqlAlchemyTenantRepository

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/knowledge-sources",
    tags=["knowledge"],
)

KnowledgeTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
KnowledgeDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
ArticleText = Annotated[str, StringConstraints(min_length=1, max_length=MAX_ARTICLE_CHARACTERS)]

tenant_repository = SqlAlchemyTenantRepository()
knowledge_service = KnowledgeService(
    SqlAlchemyKnowledgeRepository(), TenantAuthorizer(tenant_repository)
)


def get_knowledge_service() -> KnowledgeService:
    return knowledge_service


KnowledgeServiceDependency = Annotated[KnowledgeService, Depends(get_knowledge_service)]


def get_knowledge_storage(request: Request) -> ObjectStorage:
    storage: object = request.app.state.knowledge_storage
    if not isinstance(storage, ObjectStorage):
        raise RuntimeError("knowledge storage is not configured")
    return storage


def get_document_extractor(request: Request) -> DocumentExtractor:
    extractor: object = request.app.state.document_extractor
    if not isinstance(extractor, DocumentExtractor):
        raise RuntimeError("document extractor is not configured")
    return extractor


KnowledgeStorageDependency = Annotated[ObjectStorage, Depends(get_knowledge_storage)]
DocumentExtractorDependency = Annotated[DocumentExtractor, Depends(get_document_extractor)]


def get_ingestion_coordinator(
    service: KnowledgeServiceDependency,
    storage: KnowledgeStorageDependency,
    extractor: DocumentExtractorDependency,
) -> KnowledgeIngestionCoordinator:
    settings = get_settings()
    return KnowledgeIngestionCoordinator(
        service,
        storage,
        extractor,
        maximum_upload_bytes=settings.knowledge_max_upload_bytes,
        processing_stale_seconds=settings.knowledge_processing_stale_seconds,
    )


KnowledgeIngestionDependency = Annotated[
    KnowledgeIngestionCoordinator, Depends(get_ingestion_coordinator)
]


class KnowledgeVersionResponse(BaseModel):
    id: UUID
    version_number: int
    status: KnowledgeProcessingStatus
    original_filename: str | None
    media_type: str | None
    size_bytes: int | None
    processing_attempts: int
    processing_started_at: datetime | None
    processed_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, version: KnowledgeSourceVersion) -> "KnowledgeVersionResponse":
        return cls(
            id=version.id,
            version_number=version.version_number,
            status=version.status,
            original_filename=version.original_filename,
            media_type=version.media_type,
            size_bytes=version.size_bytes,
            processing_attempts=version.processing_attempts,
            processing_started_at=version.processing_started_at,
            processed_at=version.processed_at,
            failure_code=version.failure_code,
            failure_message=version.failure_message,
            created_at=version.created_at,
            updated_at=version.updated_at,
        )


class KnowledgeSourceResponse(BaseModel):
    id: UUID
    organization_id: UUID
    kind: KnowledgeSourceKind
    title: str
    description: str | None
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    current_version: KnowledgeVersionResponse

    @classmethod
    def from_domain(cls, source: KnowledgeSource) -> "KnowledgeSourceResponse":
        return cls(
            id=source.id,
            organization_id=source.organization_id,
            kind=source.kind,
            title=source.title,
            description=source.description,
            created_by_user_id=source.created_by_user_id,
            updated_by_user_id=source.updated_by_user_id,
            created_at=source.created_at,
            updated_at=source.updated_at,
            current_version=KnowledgeVersionResponse.from_domain(source.current_version),
        )


class KnowledgeSourcePageResponse(BaseModel):
    items: list[KnowledgeSourceResponse]
    next_cursor: str | None


class ArticleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: KnowledgeTitle
    description: KnowledgeDescription | None = None
    text: ArticleText


class ArticleContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: ArticleText


class KnowledgeMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: KnowledgeTitle | None = None
    description: KnowledgeDescription | None = None

    @model_validator(mode="after")
    def require_change(self) -> "KnowledgeMetadataRequest":
        if not self.model_fields_set:
            raise ValueError("at least one metadata field is required")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


class KnowledgeContentResponse(BaseModel):
    source_id: UUID
    version_id: UUID
    version_number: int
    kind: KnowledgeSourceKind
    raw_text: str | None
    normalized_text: str
    locator_map: dict[str, Any]


@router.get("", response_model=KnowledgeSourcePageResponse, summary="List knowledge sources")
async def list_knowledge_sources(
    organization_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: KnowledgeServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
    kind: KnowledgeSourceKind | None = None,
    processing_status: KnowledgeProcessingStatus | None = None,
) -> KnowledgeSourcePageResponse:
    page = await service.list_sources(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        limit=limit,
        cursor=cursor,
        kind=kind,
        status=processing_status,
    )
    return KnowledgeSourcePageResponse(
        items=[KnowledgeSourceResponse.from_domain(source) for source in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/articles",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a knowledge article",
)
async def create_article(
    organization_id: UUID,
    body: ArticleCreateRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: KnowledgeServiceDependency,
) -> KnowledgeSourceResponse:
    source = await service.create_article(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        title=body.title,
        description=body.description,
        raw_text=body.text,
    )
    return KnowledgeSourceResponse.from_domain(source)


@router.post(
    "/documents",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a knowledge document",
)
async def create_document(
    organization_id: UUID,
    actor: CurrentActor,
    database: CurrentDatabase,
    coordinator: KnowledgeIngestionDependency,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
    description: Annotated[str | None, Form(max_length=2000)] = None,
) -> KnowledgeSourceResponse:
    filename = safe_upload_filename(file.filename)
    normalized_title = default_document_title(filename) if title is None else title.strip()
    normalized_description = None if description is None else description.strip()
    if not normalized_title or (description is not None and not normalized_description):
        raise KnowledgeInvalidDocumentError

    def session_factory() -> AbstractAsyncContextManager[AsyncSession]:
        return database.session_for(actor)

    source = await coordinator.create_document(
        session_factory,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        title=normalized_title,
        description=normalized_description,
        upload=file,
    )
    return KnowledgeSourceResponse.from_domain(source)


@router.get(
    "/{source_id}", response_model=KnowledgeSourceResponse, summary="Get a knowledge source"
)
async def get_knowledge_source(
    organization_id: UUID,
    source_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: KnowledgeServiceDependency,
) -> KnowledgeSourceResponse:
    source = await service.get_source(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
    )
    return KnowledgeSourceResponse.from_domain(source)


@router.get(
    "/{source_id}/content",
    response_model=KnowledgeContentResponse,
    summary="Get normalized knowledge content",
)
async def get_knowledge_content(
    organization_id: UUID,
    source_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: KnowledgeServiceDependency,
) -> KnowledgeContentResponse:
    source = await service.get_content(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
    )
    version = source.current_version
    if version.normalized_text is None or version.locator_map is None:
        raise RuntimeError("ready knowledge content is incomplete")
    return KnowledgeContentResponse(
        source_id=source.id,
        version_id=version.id,
        version_number=version.version_number,
        kind=source.kind,
        raw_text=version.raw_text,
        normalized_text=version.normalized_text,
        locator_map=version.locator_map,
    )


@router.patch(
    "/{source_id}",
    response_model=KnowledgeSourceResponse,
    summary="Update knowledge source metadata",
)
async def update_knowledge_metadata(
    organization_id: UUID,
    source_id: UUID,
    body: KnowledgeMetadataRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: KnowledgeServiceDependency,
) -> KnowledgeSourceResponse:
    source = await service.update_metadata(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
        title=body.title,
        description=body.description,
        description_is_set="description" in body.model_fields_set,
    )
    return KnowledgeSourceResponse.from_domain(source)


@router.put(
    "/{source_id}/content",
    response_model=KnowledgeSourceResponse,
    summary="Replace article content",
)
async def replace_article_content(
    organization_id: UUID,
    source_id: UUID,
    body: ArticleContentRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: KnowledgeServiceDependency,
) -> KnowledgeSourceResponse:
    source = await service.replace_article_content(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
        raw_text=body.text,
    )
    return KnowledgeSourceResponse.from_domain(source)


@router.post(
    "/{source_id}/retry",
    response_model=KnowledgeSourceResponse,
    summary="Retry document processing",
)
async def retry_document_processing(
    organization_id: UUID,
    source_id: UUID,
    actor: CurrentActor,
    database: CurrentDatabase,
    coordinator: KnowledgeIngestionDependency,
) -> KnowledgeSourceResponse:
    def session_factory() -> AbstractAsyncContextManager[AsyncSession]:
        return database.session_for(actor)

    source = await coordinator.retry_document(
        session_factory,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
    )
    return KnowledgeSourceResponse.from_domain(source)


def _file_chunks(stream: BinaryIO) -> Iterator[bytes]:
    with stream:
        while chunk := stream.read(64 * 1024):
            yield chunk


@router.get("/{source_id}/file", summary="Download the original knowledge document")
async def download_original_document(
    organization_id: UUID,
    source_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: KnowledgeServiceDependency,
    storage: KnowledgeStorageDependency,
) -> StreamingResponse:
    file_object = await service.get_file_for_download(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
    )
    stream = await storage.open(file_object.storage_key)
    encoded_filename = quote(file_object.original_filename, safe="")
    return StreamingResponse(
        _file_chunks(stream),
        media_type=file_object.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(file_object.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge source",
)
async def delete_knowledge_source(
    organization_id: UUID,
    source_id: UUID,
    actor: CurrentActor,
    database: CurrentDatabase,
    coordinator: KnowledgeIngestionDependency,
) -> Response:
    def session_factory() -> AbstractAsyncContextManager[AsyncSession]:
        return database.session_for(actor)

    await coordinator.delete_source(
        session_factory,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
