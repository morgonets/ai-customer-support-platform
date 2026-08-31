import pytest

from app.knowledge.errors import KnowledgeContentEmptyError, KnowledgeContentTooLargeError
from app.knowledge.normalization import article_locator_map, normalize_text


def test_normalize_text_preserves_content_and_removes_unsafe_formatting() -> None:
    normalized = normalize_text("First line  \r\nSecond\x00\tline\r\n")

    assert normalized == "First line\nSecond\tline"
    assert article_locator_map(normalized) == {
        "schema_version": 1,
        "segments": [{"kind": "text", "start": 0, "end": len(normalized)}],
    }


def test_normalize_text_rejects_empty_and_oversized_content() -> None:
    with pytest.raises(KnowledgeContentEmptyError):
        normalize_text(" \n\t ")
    with pytest.raises(KnowledgeContentTooLargeError):
        normalize_text("abc", maximum_characters=2)
