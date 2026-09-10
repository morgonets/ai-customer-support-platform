from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

GenerationStatus = Literal["queued", "processing", "ready", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class EmbeddingProfile:
    id: UUID
    profile_key: str
    provider: str
    model: str
    model_revision: str | None
    dimensions: int


@dataclass(frozen=True, slots=True)
class Chunk:
    id: UUID
    ordinal: int
    content: str
    start_char: int
    end_char: int
    content_sha256: str
    locator: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChunkSet:
    id: UUID
    fingerprint: str
    normalized_content_sha256: str
    chunks: tuple[Chunk, ...]


@dataclass(frozen=True, slots=True)
class ClaimedGeneration:
    id: UUID
    organization_id: UUID
    source_id: UUID
    version_id: UUID
    profile: EmbeddingProfile
    attempt_count: int
    lease_token: UUID
    normalized_text: str
    normalization_version: int
    locator_map: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IndexGeneration:
    id: UUID
    version_id: UUID
    profile_key: str
    generation_number: int
    status: GenerationStatus
    is_active: bool
    attempt_count: int
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    chunk_id: UUID
    source_id: UUID
    version_id: UUID
    version_number: int
    source_title: str
    source_kind: str
    content: str
    locator: dict[str, Any]
    vector_score: float | None = None
    lexical_score: float | None = None


@dataclass(frozen=True, slots=True)
class RankedEvidence:
    evidence_id: str
    candidate: RetrievalCandidate
    score: float


@dataclass(frozen=True, slots=True)
class GeneratedPart:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GenerationResult:
    parts: tuple[GeneratedPart, ...]
    insufficient_context: bool


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: UUID
    version_id: UUID
    version_number: int
    source_title: str
    source_kind: str
    locator: dict[str, Any]
    excerpt: str
    answer_start: int
    answer_end: int


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    insufficient_context: bool
    citations: tuple[Citation, ...]
