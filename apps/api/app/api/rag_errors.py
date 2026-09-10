from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.errors import ErrorBody, ErrorEnvelope
from app.rag.errors import RagError


async def rag_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RagError):
        raise exc
    request_id = str(getattr(request.state, "request_id", "unavailable"))
    envelope = ErrorEnvelope(
        error=ErrorBody(code=exc.code, message=exc.safe_message, request_id=request_id)
    )
    return JSONResponse(status_code=exc.status_code, content=envelope.model_dump())
