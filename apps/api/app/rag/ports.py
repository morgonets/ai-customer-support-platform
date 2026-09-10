from collections.abc import Sequence
from typing import Protocol

from app.rag.models import GenerationResult, RankedEvidence


class EmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def embed_documents(
        self, texts: Sequence[str], *, model: str, dimensions: int
    ) -> list[list[float]]: ...

    async def embed_query(self, text: str, *, model: str, dimensions: int) -> list[float]: ...


class GenerationProvider(Protocol):
    async def generate(
        self, question: str, evidence: Sequence[RankedEvidence]
    ) -> GenerationResult: ...


class RagTelemetry(Protocol):
    def indexing_completed(self, *, provider: str, chunk_count: int, elapsed_ms: int) -> None: ...

    def retrieval_completed(
        self, *, vector_candidates: int, lexical_candidates: int, selected: int, elapsed_ms: int
    ) -> None: ...

    def answer_completed(
        self, *, insufficient_context: bool, citation_count: int, elapsed_ms: int
    ) -> None: ...
