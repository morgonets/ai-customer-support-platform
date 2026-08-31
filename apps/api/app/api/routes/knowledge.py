from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.api.dependencies import CurrentActor, CurrentSession
from app.knowledge.models import (
    KnowledgeProcessingStatus,
    KnowledgeSource,
    KnowledgeSourceKind,
    KnowledgeSourceVersion,
)
from app.knowledge.normalization import MAX_ARTICLE_CHARACTERS
from app.knowledge.repository import SqlAlchemyKnowledgeRepository
from app.knowledge.service import KnowledgeService
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
