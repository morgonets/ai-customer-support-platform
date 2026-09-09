import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.rag.models import Chunk, ChunkSet

CHUNKER_NAME = "reference-character-window"
CHUNKER_VERSION = "1"
DEFAULT_TARGET_CHARACTERS = 1600
DEFAULT_OVERLAP_CHARACTERS = 200
MAX_CHUNK_CHARACTERS = 2000


@dataclass(frozen=True, slots=True)
class ReferenceChunker:
    target_characters: int = DEFAULT_TARGET_CHARACTERS
    overlap_characters: int = DEFAULT_OVERLAP_CHARACTERS

    def __post_init__(self) -> None:
        if not 1 <= self.target_characters <= MAX_CHUNK_CHARACTERS:
            raise ValueError("target_characters must be between 1 and 2000")
        if not 0 <= self.overlap_characters < self.target_characters:
            raise ValueError("overlap_characters must be smaller than target_characters")

    @property
    def config(self) -> dict[str, int]:
        return {
            "target_characters": self.target_characters,
            "overlap_characters": self.overlap_characters,
        }

    @property
    def fingerprint(self) -> str:
        return _sha256(
            _canonical_json(
                {"name": CHUNKER_NAME, "version": CHUNKER_VERSION, "config": self.config}
            )
        )

    def chunk(
        self,
        *,
        organization_id: UUID,
        source_id: UUID,
        version_id: UUID,
        normalized_text: str,
        normalization_version: int,
        locator_map: dict[str, Any],
    ) -> ChunkSet:
        if not normalized_text:
            raise ValueError("normalized_text must not be empty")
        content_hash = _sha256(normalized_text)
        set_identity = (
            f"rag-chunk-set:{organization_id}:{source_id}:{version_id}:"
            f"{normalization_version}:{content_hash}:{self.fingerprint}"
        )
        chunk_set_id = uuid5(NAMESPACE_URL, set_identity)
        chunks: list[Chunk] = []
        start = 0
        ordinal = 0
        while True:
            end = min(start + self.target_characters, len(normalized_text))
            if end < len(normalized_text):
                boundary = normalized_text.rfind("\n\n", start + 1, end + 1)
                if boundary > start:
                    end = boundary
            content = normalized_text[start:end]
            chunk_id = uuid5(NAMESPACE_URL, f"{chunk_set_id}:{ordinal}:{start}:{end}")
            chunks.append(
                Chunk(
                    id=chunk_id,
                    ordinal=ordinal,
                    content=content,
                    start_char=start,
                    end_char=end,
                    content_sha256=_sha256(content),
                    locator=_slice_locator(locator_map, start, end),
                )
            )
            if end == len(normalized_text):
                break
            start = max(start + 1, end - self.overlap_characters)
            ordinal += 1
        return ChunkSet(
            id=chunk_set_id,
            fingerprint=self.fingerprint,
            normalized_content_sha256=content_hash,
            chunks=tuple(chunks),
        )


def _slice_locator(locator_map: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    if locator_map.get("schema_version") != 1 or not isinstance(locator_map.get("segments"), list):
        raise ValueError("unsupported locator_map")
    locations: list[dict[str, Any]] = []
    for raw in locator_map["segments"]:
        if not isinstance(raw, dict):
            raise ValueError("invalid locator segment")
        segment_start = raw.get("start")
        segment_end = raw.get("end")
        if not isinstance(segment_start, int) or not isinstance(segment_end, int):
            raise ValueError("invalid locator segment bounds")
        if segment_start < end and segment_end > start:
            location = dict(raw)
            location["chunk_start"] = max(segment_start, start) - start
            location["chunk_end"] = min(segment_end, end) - start
            locations.append(location)
    if not locations:
        raise ValueError("chunk has no source locator")
    return {"schema_version": 1, "start": start, "end": end, "locations": locations}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
