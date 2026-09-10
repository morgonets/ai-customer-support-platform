from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.api.dependencies import CurrentActor, CurrentSession
from app.api.rag_dependencies import RagServiceDependency
from app.rag.models import Answer, Citation, IndexGeneration

router = APIRouter(prefix="/api/v1/organizations/{organization_id}", tags=["rag"])
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
ProfileKey = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,99}$", min_length=1, max_length=100)
]


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Question


class CitationResponse(BaseModel):
    source_id: UUID
    version_id: UUID
    version_number: int
    source_title: str
    source_kind: str
    locator: dict[str, Any]
    excerpt: str
    answer_start: int
    answer_end: int

    @classmethod
    def from_domain(cls, citation: Citation) -> "CitationResponse":
        return cls(**{field: getattr(citation, field) for field in cls.model_fields})


class AnswerResponse(BaseModel):
    answer: str
    insufficient_context: bool
    citations: list[CitationResponse]

    @classmethod
    def from_domain(cls, answer: Answer) -> "AnswerResponse":
        return cls(
            answer=answer.text,
            insufficient_context=answer.insufficient_context,
            citations=[CitationResponse.from_domain(item) for item in answer.citations],
        )


class GenerationResponse(BaseModel):
    id: UUID
    version_id: UUID
    profile_key: str
    generation_number: int
    status: str
    is_active: bool
    attempt_count: int
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_domain(cls, generation: IndexGeneration) -> "GenerationResponse":
        return cls(**{field: getattr(generation, field) for field in cls.model_fields})


class GenerationPageResponse(BaseModel):
    items: list[GenerationResponse]


class ProfileMigrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_key: ProfileKey


@router.post("/answers", response_model=AnswerResponse, summary="Generate a grounded answer")
async def answer_question(
    organization_id: UUID,
    body: AnswerRequest,
    actor: CurrentActor,
    session: CurrentSession,
    service: RagServiceDependency,
) -> AnswerResponse:
    answer = await service.answer(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        question=body.question,
    )
    return AnswerResponse.from_domain(answer)


@router.get(
    "/knowledge-sources/{source_id}/index-generations",
    response_model=GenerationPageResponse,
    summary="List knowledge index generations",
)
async def list_index_generations(
    organization_id: UUID,
    source_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: RagServiceDependency,
) -> GenerationPageResponse:
    generations = await service.list_generations(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
    )
    return GenerationPageResponse(
        items=[GenerationResponse.from_domain(item) for item in generations]
    )


@router.post(
    "/knowledge-sources/{source_id}/index-generations",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a new knowledge index generation",
)
async def reindex_source(
    organization_id: UUID,
    source_id: UUID,
    request: Request,
    actor: CurrentActor,
    session: CurrentSession,
    service: RagServiceDependency,
) -> GenerationResponse:
    generation = await service.reindex(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
        request_id=UUID(request.state.request_id),
    )
    return GenerationResponse.from_domain(generation)


@router.post(
    "/knowledge-sources/{source_id}/index-generations/{generation_id}/retry",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed knowledge index generation",
)
async def retry_index_generation(
    organization_id: UUID,
    source_id: UUID,
    generation_id: UUID,
    actor: CurrentActor,
    session: CurrentSession,
    service: RagServiceDependency,
) -> GenerationResponse:
    generation = await service.retry(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        source_id=source_id,
        generation_id=generation_id,
    )
    return GenerationResponse.from_domain(generation)


@router.post(
    "/rag-profile-migrations",
    response_model=GenerationPageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Build generations for a replacement embedding profile",
)
async def migrate_embedding_profile(
    organization_id: UUID,
    body: ProfileMigrationRequest,
    request: Request,
    actor: CurrentActor,
    session: CurrentSession,
    service: RagServiceDependency,
) -> GenerationPageResponse:
    generations = await service.migrate_profile(
        session,
        actor_user_id=actor.user_id,
        organization_id=organization_id,
        profile_key=body.profile_key,
        request_id=UUID(request.state.request_id),
    )
    return GenerationPageResponse(
        items=[GenerationResponse.from_domain(item) for item in generations]
    )
