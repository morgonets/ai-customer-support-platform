class RagError(Exception):
    code = "rag_error"
    safe_message = "The RAG operation could not be completed."
    status_code = 400


class RagNotConfiguredError(RagError):
    code = "rag_not_configured"
    safe_message = "Retrieval is not configured for this organization."
    status_code = 409


class RagGenerationNotFoundError(RagError):
    code = "rag_generation_not_found"
    safe_message = "The index generation was not found."
    status_code = 404


class RagProfileNotFoundError(RagError):
    code = "rag_profile_not_found"
    safe_message = "The embedding profile was not found."
    status_code = 404


class RagProviderUnavailableError(RagError):
    code = "rag_provider_unavailable"
    safe_message = "The answer provider is temporarily unavailable."
    status_code = 503
