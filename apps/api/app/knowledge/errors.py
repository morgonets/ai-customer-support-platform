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
