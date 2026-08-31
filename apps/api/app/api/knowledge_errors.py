from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import ApiError, api_error_handler
from app.knowledge.errors import (
    InvalidKnowledgeCursorError,
    KnowledgeContentEmptyError,
    KnowledgeContentTooLargeError,
    KnowledgeContentUnavailableError,
    KnowledgeError,
    KnowledgeFileTooLargeError,
    KnowledgeInvalidDocumentError,
    KnowledgeProcessingInProgressError,
    KnowledgeProcessingNotRetryableError,
    KnowledgeSourceKindError,
    KnowledgeSourceNotFoundError,
    KnowledgeStorageUnavailableError,
    KnowledgeUnsupportedMediaTypeError,
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
    elif isinstance(exc, KnowledgeFileTooLargeError):
        api_error = ApiError(
            status_code=413,
            code="file_too_large",
            message="The uploaded file is too large.",
        )
    elif isinstance(exc, KnowledgeUnsupportedMediaTypeError):
        api_error = ApiError(
            status_code=415,
            code="unsupported_media_type",
            message="The uploaded file type is not supported.",
        )
    elif isinstance(exc, KnowledgeInvalidDocumentError):
        api_error = ApiError(
            status_code=422,
            code="invalid_document",
            message="The uploaded document is invalid.",
        )
    elif isinstance(exc, KnowledgeStorageUnavailableError):
        api_error = ApiError(
            status_code=503,
            code="storage_unavailable",
            message="Knowledge file storage is unavailable.",
        )
    elif isinstance(exc, KnowledgeProcessingInProgressError):
        api_error = ApiError(
            status_code=409,
            code="processing_in_progress",
            message="The knowledge source is already being processed.",
        )
    elif isinstance(exc, KnowledgeProcessingNotRetryableError):
        api_error = ApiError(
            status_code=409,
            code="processing_not_retryable",
            message="The knowledge source is not eligible for retry.",
        )
    else:  # pragma: no cover - forces explicit review for every new knowledge error.
        raise exc
    return await api_error_handler(request, api_error)
