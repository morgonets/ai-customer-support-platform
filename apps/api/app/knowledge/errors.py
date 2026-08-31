class KnowledgeError(Exception):
    """Base class for expected knowledge-domain failures."""


class KnowledgeSourceNotFoundError(KnowledgeError):
    pass


class InvalidKnowledgeCursorError(KnowledgeError):
    pass


class KnowledgeContentEmptyError(KnowledgeError):
    pass


class KnowledgeContentTooLargeError(KnowledgeError):
    pass


class KnowledgeSourceKindError(KnowledgeError):
    pass


class KnowledgeContentUnavailableError(KnowledgeError):
    pass


class KnowledgeFileTooLargeError(KnowledgeError):
    pass


class KnowledgeUnsupportedMediaTypeError(KnowledgeError):
    pass


class KnowledgeInvalidDocumentError(KnowledgeError):
    pass


class KnowledgeStorageUnavailableError(KnowledgeError):
    pass


class KnowledgeProcessingInProgressError(KnowledgeError):
    pass


class KnowledgeProcessingNotRetryableError(KnowledgeError):
    pass


class DocumentExtractionError(Exception):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
