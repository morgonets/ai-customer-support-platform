from uuid import UUID

import pytest

from app.rag.chunking import ReferenceChunker

ORGANIZATION_ID = UUID("10000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("20000000-0000-0000-0000-000000000001")
VERSION_ID = UUID("30000000-0000-0000-0000-000000000001")


@pytest.mark.parametrize(
    ("target", "overlap", "message"),
    [(0, 0, "target"), (2001, 0, "target"), (10, -1, "overlap"), (10, 10, "overlap")],
)
def test_reference_chunker_rejects_invalid_configuration(
    target: int, overlap: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ReferenceChunker(target_characters=target, overlap_characters=overlap)


def test_reference_chunking_is_deterministic_exact_and_location_aware() -> None:
    text = "First paragraph.\n\nSecond paragraph is longer.\n\nThird."
    locator = {
        "schema_version": 1,
        "segments": [
            {"kind": "page", "page": 1, "start": 0, "end": 18},
            {"kind": "page", "page": 2, "start": 18, "end": len(text)},
        ],
    }
    chunker = ReferenceChunker(target_characters=35, overlap_characters=5)

    first = chunker.chunk(
        organization_id=ORGANIZATION_ID,
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        normalized_text=text,
        normalization_version=1,
        locator_map=locator,
    )
    second = chunker.chunk(
        organization_id=ORGANIZATION_ID,
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        normalized_text=text,
        normalization_version=1,
        locator_map=locator,
    )

    assert first == second
    assert first.fingerprint == chunker.fingerprint
    assert chunker.config == {"target_characters": 35, "overlap_characters": 5}
    assert len(first.chunks) == 3
    for ordinal, chunk in enumerate(first.chunks):
        assert chunk.ordinal == ordinal
        assert chunk.content == text[chunk.start_char : chunk.end_char]
        assert chunk.end_char - chunk.start_char <= 35
        assert chunk.locator["schema_version"] == 1
        assert chunk.locator["locations"]
    assert len(first.chunks[1].locator["locations"]) == 2


def test_reference_chunking_handles_hard_windows_and_rejects_invalid_inputs() -> None:
    chunker = ReferenceChunker(target_characters=4, overlap_characters=1)
    valid_locator = {
        "schema_version": 1,
        "segments": [{"kind": "text", "start": 0, "end": 6}],
    }
    result = chunker.chunk(
        organization_id=ORGANIZATION_ID,
        source_id=SOURCE_ID,
        version_id=VERSION_ID,
        normalized_text="abcdef",
        normalization_version=1,
        locator_map=valid_locator,
    )
    assert [chunk.content for chunk in result.chunks] == ["abcd", "def"]

    with pytest.raises(ValueError, match="must not be empty"):
        chunker.chunk(
            organization_id=ORGANIZATION_ID,
            source_id=SOURCE_ID,
            version_id=VERSION_ID,
            normalized_text="",
            normalization_version=1,
            locator_map=valid_locator,
        )
    for locator in (
        {},
        {"schema_version": 1, "segments": ["invalid"]},
        {"schema_version": 1, "segments": [{"kind": "text", "start": "0", "end": 6}]},
        {"schema_version": 1, "segments": [{"kind": "text", "start": 7, "end": 8}]},
    ):
        with pytest.raises(ValueError):
            chunker.chunk(
                organization_id=ORGANIZATION_ID,
                source_id=SOURCE_ID,
                version_id=VERSION_ID,
                normalized_text="abcdef",
                normalization_version=1,
                locator_map=locator,
            )
