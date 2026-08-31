from app.knowledge.errors import KnowledgeContentEmptyError, KnowledgeContentTooLargeError

MAX_ARTICLE_CHARACTERS = 500_000
MAX_NORMALIZED_CHARACTERS = 2_000_000
NORMALIZATION_VERSION = 1


def normalize_text(value: str, *, maximum_characters: int = MAX_NORMALIZED_CHARACTERS) -> str:
    normalized_newlines = value.replace("\r\n", "\n").replace("\r", "\n")
    safe_characters = "".join(
        character
        for character in normalized_newlines
        if character in ("\n", "\t") or ord(character) >= 32
    )
    normalized = "\n".join(line.rstrip(" \t") for line in safe_characters.split("\n")).strip("\n")
    if normalized.strip() == "":
        raise KnowledgeContentEmptyError
    if len(normalized) > maximum_characters:
        raise KnowledgeContentTooLargeError
    return normalized


def article_locator_map(normalized_text: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "segments": [{"kind": "text", "start": 0, "end": len(normalized_text)}],
    }
