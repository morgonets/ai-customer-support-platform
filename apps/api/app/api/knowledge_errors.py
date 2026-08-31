from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import ApiError, api_error_handler
from app.knowledge.errors import (
    InvalidKnowledgeCursorError,
    KnowledgeContentEmptyError,
    KnowledgeContentTooLargeError,
    KnowledgeContentUnavailableError,
    KnowledgeError,
    KnowledgeSourceKindError,
    KnowledgeSourceNotFoundError,
)


async def knowledge_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, KnowledgeError):
        raise exc
    if isinstance(exc, KnowledgeSourceNotFoundError):
        api_error = ApiError(
            status_code=404,
            code="knowledge_source_not_found",
            message="The knowledge source was not found.",
        )
    elif isinstance(exc, InvalidKnowledgeCursorError):
        api_error = ApiError(
            status_code=422,
            code="invalid_cursor",
            message="The pagination cursor is invalid.",
        )
    elif isinstance(exc, KnowledgeContentEmptyError):
        api_error = ApiError(
            status_code=422,
            code="invalid_knowledge_content",
            message="Knowledge content must contain readable text.",
        )
    elif isinstance(exc, KnowledgeContentTooLargeError):
        api_error = ApiError(
            status_code=422,
            code="normalized_content_too_large",
            message="The normalized knowledge content is too large.",
        )
    elif isinstance(exc, KnowledgeSourceKindError):
        api_error = ApiError(
            status_code=409,
            code="knowledge_source_kind_mismatch",
            message="This operation is not supported for the knowledge source type.",
        )
    elif isinstance(exc, KnowledgeContentUnavailableError):
        api_error = ApiError(
            status_code=409,
            code="knowledge_content_unavailable",
            message="Normalized knowledge content is not available.",
        )
    else:  # pragma: no cover - forces explicit review for every new knowledge error.
        raise exc
    return await api_error_handler(request, api_error)
