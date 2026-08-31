from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

KnowledgeSourceKind = Literal["article", "document"]
KnowledgeProcessingStatus = Literal["processing", "ready", "failed"]


@dataclass(frozen=True, slots=True)
class KnowledgeSourceVersion:
    id: UUID
    organization_id: UUID
    source_id: UUID
    kind: KnowledgeSourceKind
    version_number: int
    is_current: bool
    status: KnowledgeProcessingStatus
    raw_text: str | None
    normalized_text: str | None
    normalization_version: int
    locator_map: dict[str, object] | None
    original_filename: str | None
    media_type: str | None
    size_bytes: int | None
    sha256: str | None
    extractor_name: str | None
    extractor_version: str | None
    processing_attempts: int
    processing_started_at: datetime | None
    processed_at: datetime | None
    failure_code: str | None
    failure_message: str | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    id: UUID
    organization_id: UUID
    kind: KnowledgeSourceKind
    title: str
    description: str | None
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    current_version: KnowledgeSourceVersion


@dataclass(frozen=True, slots=True)
class KnowledgeSourcePage:
    items: list[KnowledgeSource]
    next_cursor: str | None
